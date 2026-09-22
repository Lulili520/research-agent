"""验证正文证据与报告读者契约的关系，不把合成测试当人类理解实验。"""
from copy import deepcopy
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


if __name__ == "__main__":
    unittest.main()
