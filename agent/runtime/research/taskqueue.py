"""Persistent host-driven evidence tasks; never executes tools or advances stages."""
import argparse
import hashlib
import json
from pathlib import Path
from graphlib import TopologicalSorter, CycleError
import re
import secrets

try:
    from .storage import now, project, project_lock, read_json, write_json_atomic, verify_events
    from .gates import require_current_policy
except ImportError:
    from storage import now, project, project_lock, read_json, write_json_atomic, verify_events
    from gates import require_current_policy


class TaskQueue:
    """Serialize task transitions and retain attempts in one atomic document."""

    def __init__(self, path):
        self.root = project(str(path))
        self.base = Path(self.root).resolve()
        self.path = self.root / 'control/tasks.json'

    def snapshot(self, paths):
        result = {}
        for name in paths:
            relative = Path(name)
            if '..' in relative.parts or relative.is_absolute() or not relative.parts:
                raise ValueError('artifact must be a project-relative path without traversal')
            path = self.base / relative
            if any((self.base / Path(*relative.parts[:index])).is_symlink()
                   for index in range(1, len(relative.parts) + 1)):
                raise ValueError('artifact paths must not contain symbolic links')
            resolved = path.resolve()
            if (Path(name).is_absolute() or not resolved.is_relative_to(self.base)
                    or resolved.is_relative_to(self.base / 'control')):
                raise ValueError('artifact must be inside .research and outside control')
            if not resolved.is_file() or not resolved.stat().st_size:
                raise ValueError(f'missing or empty artifact: {name}')
            with resolved.open('rb') as stream:
                result[resolved.relative_to(self.base).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
        return result

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
            raise ValueError('unsupported task queue version; explicit migration required')
        tasks = data.get('tasks')
        if not isinstance(tasks, dict):
            raise ValueError('invalid task queue: tasks must be an object')
        for key, task in tasks.items():
            if not isinstance(key, str) or not key.strip() or not isinstance(task, dict):
                raise ValueError('invalid task queue: malformed task')
            if (task.get('status') not in ('pending', 'running', 'complete', 'failed', 'cancelled')
                    or type(task.get('attempts')) is not int or task['attempts'] < 0
                    or not isinstance(task.get('history'), list)
                    or any(not isinstance(task.get(field), str) or not task[field].strip()
                           for field in ('question', 'acceptance'))):
                raise ValueError(f'invalid task record: {key}')
            for field in ('inputs', 'outputs'):
                files = task.get(field)
                if not isinstance(files, dict) or any(
                        not isinstance(name, str) or not isinstance(digest, str)
                        or not re.fullmatch(r'[0-9a-f]{64}', digest)
                        for name, digest in files.items()):
                    raise ValueError(f'invalid {field} hashes: {key}')
            dependencies = task.get('dependencies')
            if (not isinstance(dependencies, list)
                    or any(not isinstance(dep, str) or dep not in tasks for dep in dependencies)
                    or len(set(dependencies)) != len(dependencies)):
                raise ValueError(f'invalid task dependencies: {key}')
            versions = task.get('dependency_attempts', {})
            if not isinstance(versions, dict):
                raise ValueError(f'invalid dependency versions: {key}')
            if task['status'] in ('running', 'complete'):
                if (task['attempts'] == 0 or not isinstance(versions, dict)
                        or set(versions) != set(dependencies)
                        or any(type(v) is not int or v < 1 for v in versions.values())):
                    raise ValueError(f'invalid dependency versions: {key}')
            if task['status'] == 'running' and (
                    not isinstance(task.get('token'), str) or not task['token']
                    or not isinstance(task.get('owner'), str) or not task['owner'].strip()):
                raise ValueError(f'invalid running claim: {key}')
            if task['status'] == 'complete' and not task['outputs']:
                raise ValueError(f'complete task has no artifacts: {key}')
        try:
            return tuple(TopologicalSorter({key: task['dependencies'] for key, task in tasks.items()}).static_order())
        except CycleError as error:
            raise ValueError('invalid task queue: dependency cycle') from error

    def fresh(self, files, cache):
        for name, expected in files.items():
            if name not in cache:
                try:
                    cache[name] = self.snapshot([name]).get(name)
                except (ValueError, OSError):
                    cache[name] = None
            if cache[name] != expected:
                return False
        return True

    def evaluate(self, tasks, order):
        # Topological evaluation avoids repeated traversal of shared ancestors and
        # recursion limits. File hashes are cached only for this locked operation.
        result, cache = {}, {}
        for key in order:
            task = tasks[key]
            reasons = []
            inputs_ok = self.fresh(task['inputs'], cache)
            if not inputs_ok:
                reasons.append('inputs-missing-or-changed')
            dependencies_ok = all(result[dep]['usable'] for dep in task['dependencies'])
            if not dependencies_ok:
                reasons.append('dependencies-unusable')
            versions_ok = all(task.get('dependency_attempts', {}).get(dep) == tasks[dep]['attempts']
                              for dep in task['dependencies'])
            if task['status'] in ('running', 'complete') and not versions_ok:
                reasons.append('dependency-attempt-changed')
            outputs_ok = bool(task['outputs']) and self.fresh(task['outputs'], cache)
            if task['status'] == 'complete' and not outputs_ok:
                reasons.append('outputs-missing-or-changed')
            result[key] = dict(usable=task['status'] == 'complete' and not reasons,
                               ready=task['status'] == 'pending' and inputs_ok and dependencies_ok,
                               reasons=reasons)
        return result

    def apply(self, action, **args):
        with project_lock(self.root):
            data = read_json(self.path) if self.path.exists() else {'version': 1, 'tasks': {}}
            order = self.validate(data)
            tasks = data['tasks']
            health = self.evaluate(tasks, order)
            if action == 'list':
                return {key: dict(task, **health[key]) for key, task in tasks.items()}
            verify_events(self.root)
            require_current_policy(self.root)
            key = args['id'].strip()
            if not key:
                raise ValueError('task id must be nonempty')
            if action == 'add':
                if key in tasks:
                    raise ValueError('task id already exists')
                dependencies = list(dict.fromkeys(args.get('depends', [])))
                if any(dep not in tasks for dep in dependencies):
                    raise ValueError('dependencies must name existing tasks')
                # Only backward references are allowed, so cycles cannot be introduced.
                question, acceptance = args['question'].strip(), args['acceptance'].strip()
                if not question or not acceptance:
                    raise ValueError('question and acceptance must be nonempty')
                tasks[key] = dict(question=question, acceptance=acceptance,
                                  dependencies=dependencies, inputs=self.snapshot(args.get('inputs', [])),
                                  outputs={}, status='pending', attempts=0, history=[])
                task = tasks[key]
            else:
                if key not in tasks:
                    raise ValueError('unknown task')
                task = tasks[key]
                if action == 'claim':
                    if task['status'] != 'pending':
                        raise ValueError('task is not pending; reconcile interrupted work before retry')
                    if not health[key]['ready']:
                        raise ValueError('stale inputs or unfinished/stale dependencies')
                    owner = args['owner'].strip()
                    if not owner:
                        raise ValueError('owner must be nonempty')
                    task.update(status='running', token=secrets.token_hex(16), owner=owner,
                                attempts=task['attempts'] + 1,
                                dependency_attempts={dep: tasks[dep]['attempts'] for dep in task['dependencies']})
                elif action in ('finish', 'fail'):
                    if task['status'] != 'running' or not secrets.compare_digest(task['token'], args['token']):
                        raise ValueError('task is not running or claim token is invalid')
                    if action == 'finish':
                        outputs = self.snapshot(args.get('outputs', []))
                        if not outputs or set(outputs) & set(task['inputs']):
                            raise ValueError('finish needs distinct nonempty output artifacts')
                        if health[key]['reasons']:
                            raise ValueError('inputs or dependencies changed; reconcile before continuing')
                        if not args.get('note', '').strip():
                            raise ValueError('finish needs an acceptance explanation')
                        task.update(status='complete', outputs=outputs)
                    else:
                        if not args.get('note', '').strip():
                            raise ValueError('failure needs a reason')
                        task['status'] = 'failed'
                    task.pop('token')
                elif action == 'cancel':
                    if not args.get('note', '').strip():
                        raise ValueError('cancellation needs a reason and external-work reconciliation')
                    if task['status'] == 'cancelled':
                        raise ValueError('task is already cancelled')
                    task['status'] = 'cancelled'
                    task.pop('token', None)
                elif action == 'reconcile':
                    if not args.get('note', '').strip():
                        raise ValueError('reconciliation needs findings and a retry reason')
                    # Explicit host reconciliation only: never retry merely because time elapsed.
                    task['history'].append(dict(time=now(), action='archive-attempt',
                                                inputs=task['inputs'], outputs=task['outputs'],
                                                status=task['status'], attempt=task['attempts']))
                    task.update(status='pending', inputs=self.snapshot(task['inputs']), outputs={})
                    task.pop('token', None)
                else:
                    raise ValueError(f'unknown action: {action}')
            task['history'].append(dict(time=now(), action=action, attempt=task['attempts'],
                                        owner=task.get('owner'), note=args.get('note', '')))
            write_json_atomic(self.path, data)
            return task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', help='initialized research project')
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('list')
    add = commands.add_parser('add')
    add.add_argument('id')
    add.add_argument('--question', required=True)
    add.add_argument('--acceptance', required=True)
    add.add_argument('--inputs', nargs='*', default=[])
    add.add_argument('--depends', nargs='*', default=[])
    claim = commands.add_parser('claim')
    claim.add_argument('id')
    claim.add_argument('--owner', required=True)
    for action in ('finish', 'fail', 'reconcile', 'cancel'):
        sub = commands.add_parser(action)
        sub.add_argument('id')
        sub.add_argument('--note', required=True)
        if action in ('finish', 'fail'):
            sub.add_argument('--token', required=True)
        if action == 'finish':
            sub.add_argument('--outputs', nargs='+', required=True)
    args = vars(parser.parse_args())
    queue = TaskQueue(args.pop('project'))
    try:
        result = queue.apply(args.pop('action'), **args)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
