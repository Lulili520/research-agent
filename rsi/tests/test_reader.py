"""验证正文证据与报告读者契约的关系，不把合成测试当人类理解实验。"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rsi.runtime.contracts import ContractError, ref
from rsi.runtime.engine import Engine
from rsi.runtime.quality import report_status, validate_review
from rsi.runtime.history import restore
from rsi.tests.helpers import source, report, review_record


class ReaderContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = Engine(self.tmp.name)
        self.engine.initialize("合成解释性测试", "literature")
        self.src = source(self.engine)
        self.contract = {"audience": "只知基础算术的合成读者",
                         "assumed_knowledge": ["加法与除法"],
                         "required_checks": ["mechanism", "example"]}
        self.target = self.engine.capture({"key": "literature", "kind": "literature",
            "content": "合成例子：分数2和3，先相加得5，再各除5，权重0.4与0.6。",
            "parents": [ref(self.src)], "metadata": {"reader_contract": self.contract}}, "writer")

    def record(self):
        r = review_record(self.engine.store.read(), self.target)
        r["reader_check"] = {"audience": self.contract["audience"], "method": "model-text-audit",
            "limitations": "仅合成契约测试，无真实读者理解证据。", "exercises": [
                {"check_id": k, "question": "怎样得到权重？", "response": "2/(2+3)=0.4。",
                 "result": "supported", "evidence": [{**ref(self.target), "locator": "首段计算例子"}],
                 "gaps": [], "outside_knowledge": []} for k in self.contract["required_checks"]]}
        return r

    def test_required_reader_evidence_cannot_be_replaced_by_scientific_review(self):
        r = self.record(); del r["reader_check"]
        with self.assertRaisesRegex(ContractError, "必须实际完成"):
            self.engine.review(r, "critic")

    def test_source_only_answer_does_not_establish_report_explanation(self):
        r = self.record()
        r["reader_check"]["exercises"][0]["evidence"] = [{**ref(self.src), "locator": "Eq1"}]
        with self.assertRaisesRegex(ContractError, "定位当前正文"):
            self.engine.review(r, "critic")

    def test_background_gap_cannot_pass(self):
        r = self.record(); r["reader_check"]["exercises"][0]["outside_knowledge"] = ["正文未介绍归一化"]
        with self.assertRaisesRegex(ContractError, "不能记为 supported"):
            self.engine.review(r, "critic")

    def test_missing_declared_exercise_rejected(self):
        r = self.record(); r["reader_check"]["exercises"].pop()
        with self.assertRaisesRegex(ContractError, "未覆盖"):
            self.engine.review(r, "critic")

    def test_failed_exercise_creates_real_revision(self):
        r = self.record(); item = r["reader_check"]["exercises"][0]
        item.update(result="partial", gaps=["未解释分母来源"], finding_refs=["reader-01"])
        with self.assertRaisesRegex(ContractError, "实质整改"):
            self.engine.review(r, "critic")
        r["findings"] = [{"dimension": "explanation-quality", "severity": "major", "role": "reader",
            "review_note_id": "reader-01", "reader_check_id": "mechanism",
            "concern": "例子跳步", "location": "首段", "impact": "无法还原计算", "action": "解释分母",
            "closure_check": "只凭正文可解释分母", "evidence": [{**ref(self.target), "locator": "首段"}]}]
        self.engine.review(r, "critic")
        status = report_status(self.engine.store.read(), "literature")
        self.assertEqual(status["status"], "revise")
        self.assertEqual(status["reader"]["status"], "revise")
        self.assertTrue(any(t.get("finding_id") for t in self.engine.store.read()["tasks"].values()))

    def test_passing_audit_is_not_human_comprehension_claim(self):
        self.engine.review(self.record(), "critic")
        status = report_status(self.engine.store.read(), "literature")
        self.assertEqual(status["reader"]["status"], "text-audit-cleared")
        self.assertEqual(status["reader"]["method"], "model-text-audit")

    def test_human_test_cannot_be_declared_without_actual_protocol(self):
        r = self.record(); r["reader_check"]["method"] = "human-reader-test"
        with self.assertRaisesRegex(ContractError, "不冒充"):
            self.engine.review(r, "critic")

    def test_profile_mismatch_rejected(self):
        r = self.record(); r["reader_check"]["audience"] = "专家"
        with self.assertRaisesRegex(ContractError, "audience"):
            self.engine.review(r, "critic")

    def test_dropping_contract_requires_explicit_reason(self):
        with self.assertRaisesRegex(ContractError, "变更或移除"):
            report(self.engine, self.src)

    def test_unrelated_major_finding_does_not_route_reader_repair(self):
        r = self.record(); item = r['reader_check']['exercises'][0]
        item.update(result='partial', gaps=['正文没有解释分母'], finding_refs=['budget-01'])
        r['findings'] = [{'review_note_id': 'budget-01', 'dimension': 'evidence-comparability',
            'severity': 'major', 'role': 'reader', 'concern': '训练预算不清楚', 'location': '实验',
            'impact': '无法比较', 'action': '补查训练预算', 'closure_check': '找到预算',
            'evidence': [{**ref(self.target), 'locator': '实验'}]}]
        with self.assertRaisesRegex(ContractError, '同一读者任务'):
            self.engine.review(r, 'critic')

    def test_audience_or_checks_cannot_change_silently(self):
        for change in ({'audience': '专业研究者'}, {'required_checks': ['mechanism']},
                       {'assumed_knowledge': ['已掌握归一化']}):
            with self.subTest(change=change):
                changed = {**self.contract, **change}
                with self.assertRaisesRegex(ContractError, '变更或移除'):
                    self.engine.capture({'key': 'literature', 'kind': 'literature', 'content': '新正文',
                        'parents': [ref(self.src)], 'metadata': {'reader_contract': changed}}, 'writer')

    def test_restore_keeps_current_reader_requirements(self):
        with TemporaryDirectory() as d:
            e = Engine(d); e.initialize('合成恢复测试', 'literature'); src = source(e)
            old = report(e, src)
            e.capture({'key': 'literature', 'kind': 'literature', 'content': '教学版正文',
                'parents': [ref(src)], 'metadata': {'reader_contract': self.contract}}, 'writer')
            restored = restore(e, 'literature', 1, 'maintainer', '用户要求恢复内容')
            self.assertEqual(restored['sha256'], old['sha256'])
            self.assertEqual(restored['metadata']['reader_contract'], self.contract)
            with self.assertRaisesRegex(ContractError, '必须实际完成'):
                e.review(review_record(e.store.read(), restored), 'critic')

    def test_duplicate_checks_rejected_on_capture(self):
        bad = deepcopy(self.contract); bad["required_checks"] = ["example", "example"]
        with self.assertRaisesRegex(ContractError, "不能重复"):
            self.engine.capture({"key": "literature", "kind": "literature", "content": "x",
                "parents": [ref(self.src)], "metadata": {"reader_contract": bad}}, "writer")

    def test_reports_without_contract_are_not_reader_approved(self):
        target = self.engine.capture({"key": "literature", "kind": "literature", "content": "未声明读者契约的合成报告",
            "parents": [ref(self.src)], "metadata": {"reader_contract_change_reason": "测试移除读者契约后的未评估状态"}}, "writer")
        self.engine.review(review_record(self.engine.store.read(), target), "critic")
        status = report_status(self.engine.store.read(), "literature")
        self.assertEqual(status["reader"]["status"], "not-assessed")

    def proposal_record(self):
        """整体检查仍使用通用契约；这里的回答全是结构测试，不证明可读性。"""
        contract = {**self.contract, 'required_checks': [
            'overview-reconstruction', 'end-to-end-trace', 'priority-and-scope', 'example']}
        target = self.engine.capture({'key': 'proposal', 'kind': 'proposal',
            'content': '合成方案材料，用来测试整体理解失败不会被局部算例通过覆盖。',
            'parents': [ref(self.src)], 'metadata': {'reader_contract': contract}}, 'designer')
        record = review_record(self.engine.store.read(), target)
        record['reader_check'] = {'audience': contract['audience'], 'method': 'model-text-audit',
            'limitations': '合成接口测试，未测量真实文本理解。', 'exercises': [
                {'check_id': k, 'question': '合成检查任务', 'response': '合成回答占位用于契约验证',
                 'result': 'supported', 'evidence': [{**ref(target), 'locator': '合成正文'}],
                 'gaps': [], 'outside_knowledge': []} for k in contract['required_checks']]}
        return target, record

    def test_local_answers_cannot_replace_declared_whole_proposal_check(self):
        _, record = self.proposal_record()
        record['reader_check']['exercises'] = [item for item in record['reader_check']['exercises']
                                               if item['check_id'] != 'overview-reconstruction']
        with self.assertRaisesRegex(ContractError, '未覆盖'):
            self.engine.review(record, 'independent-reader')

    def test_whole_proposal_gap_routes_to_repair_despite_local_success(self):
        target, record = self.proposal_record()
        record['reader_check']['exercises'][0].update(result='partial',
            gaps=['算得出局部权重，但正文没有连接原问题与核心改变'], finding_refs=['whole-01'])
        record['findings'] = [{'review_note_id': 'whole-01',
            'reader_check_id': 'overview-reconstruction', 'dimension': 'mechanism-and-assumptions',
            'severity': 'major', 'role': 'designer', 'concern': '整体机制无法从正文复述',
            'location': '开头与方法之间', 'impact': '无法理解干预目的',
            'action': '重建问题到干预的解释链，而不只补充局部算例',
            'closure_check': '新正文可独立重述该关系',
            'evidence': [{**ref(target), 'locator': '合成正文'}]}]
        self.engine.review(record, 'independent-reader')
        state = self.engine.store.read()
        self.assertEqual(report_status(state, 'proposal')['status'], 'revise')
        self.assertTrue(any(t['action'] == 'repair' and t.get('target_key') == 'proposal'
                            for t in state['tasks'].values()))

    def experiment_record(self):
        """登记公开缓存样例的已知缺口；单测不自动判断自然语言方案质量。"""
        fixture = Path(__file__).parent / 'fixtures' / 'proposal-validation'
        material = self.engine.capture({'key': 'cache-request', 'kind': 'source',
            'content': (fixture / 'task.md').read_text(encoding='utf-8'),
            'metadata': {'origin': 'synthetic-test-only', 'access': 'full-text'}}, 'finder')
        contract = {'audience': '懂基础循环、均值和百分比的合成维护者',
            'assumed_knowledge': ['基础循环', '均值', '百分比'],
            'required_checks': ['overview-reconstruction', 'experiment-reconstruction',
                                'result-to-decision']}
        target = self.engine.capture({'key': 'proposal', 'kind': 'proposal',
            'content': (fixture / 'candidate-a.md').read_text(encoding='utf-8'),
            'parents': [ref(material)], 'metadata': {'reader_contract': contract}}, 'designer')
        record = review_record(self.engine.store.read(), target)
        record['reader_check'] = {'audience': contract['audience'], 'method': 'model-text-audit',
            'limitations': '人为构造的记录，用于验证发现实验缺口后的整改流转；非自动语义判断或真人测试。',
            'exercises': [
                {'check_id': 'overview-reconstruction', 'question': '实际改变了什么？',
                 'response': '旧访问计数每 100 次请求乘 0.5，使过去热点的累计优势衰减；其余淘汰规则不变。',
                 'result': 'supported', 'evidence': [{**ref(target), 'locator': '目标与思想、算法'}],
                 'gaps': [], 'outside_knowledge': []},
                {'check_id': 'experiment-reconstruction', 'question': '如何安排第一轮可判定的验证？',
                 'response': '能确定 20 个位置和三种淘汰规则，但不能生成指定请求流或安排独立重复；'
                             '正文没有流长度、生成分布、种子拆分、配对层级和可复算运行量。',
                 'result': 'partial', 'evidence': [{**ref(target), 'locator': '实验设计、指标与统计、资源与停止条件'}],
                 'gaps': ['从实验名称无法还原材料、独立重复与分析过程'], 'outside_knowledge': [],
                 'finding_refs': ['cache-experiment']},
                {'check_id': 'result-to-decision', 'question': '收益区间跨越维护门槛时如何决策？',
                 'response': '正文只写显著且可接受时继续，没有将给定收益/退化/时间门槛映射到判据，'
                             '也没有区分未达效用与精度不足，不能据正文决策。',
                 'result': 'partial', 'evidence': [{**ref(target), 'locator': '资源与停止条件'}],
                 'gaps': ['没有可应用于结果的效用与精度判据'], 'outside_knowledge': [],
                 'finding_refs': ['cache-decision']} ]}
        record['findings'] = []
        for check_id, note_id, dimension, concern, action, closure in [
            ('experiment-reconstruction', 'cache-experiment', 'implementation-specificity',
             '算法可还原但第一轮验证不可安排', '将流生成、拆分、重复、分析与预算连成一轮验证',
             '仅据新正文可列出运行量并解释每条观测如何进入比较'),
            ('result-to-decision', 'cache-decision', 'discriminating-tests',
             '区间与使用要求未连接到继续或停止', '定义支持、不利和精度不足的判定及下一动作',
             '能将三类假设结果代入规则而无须评审另定阈值')]:
            evidence = [{**ref(target), 'locator': '实验设计至资源与停止条件'}]
            record['dimensions'][dimension] = {'status': 'partial', 'reason': concern,
                                               'evidence': evidence}
            record['findings'].append({'review_note_id': note_id, 'reader_check_id': check_id,
                'dimension': dimension, 'severity': 'major', 'role': 'designer',
                'concern': concern, 'location': '实验设计至资源与停止条件',
                'impact': '无法从正文执行和判定中心验证', 'action': action,
                'closure_check': closure, 'evidence': evidence})
        return target, record

    def test_clear_algorithm_does_not_close_recorded_experiment_gap(self):
        _, record = self.experiment_record()
        self.engine.review(record, 'independent-fixture-reader')
        state = self.engine.store.read()
        self.assertEqual(report_status(state, 'proposal')['status'], 'revise')
        gaps = {finding['reader_check_id']: finding for finding in state['findings'].values()}
        self.assertEqual(set(gaps), {'experiment-reconstruction', 'result-to-decision'})
        repair_ids = {task.get('finding_id') for task in state['tasks'].values()
                      if task['action'] == 'repair'}
        self.assertTrue(all(finding['id'] in repair_ids for finding in gaps.values()))

    def test_experiment_repair_cannot_substitute_for_result_decision_check(self):
        _, record = self.experiment_record()
        record['reader_check']['exercises'][-1]['finding_refs'] = ['cache-experiment']
        with self.assertRaisesRegex(ContractError, '同一读者任务'):
            self.engine.review(record, 'independent-fixture-reader')


if __name__ == "__main__":
    unittest.main()
