"""六维研究框架、社交观点真实性边界及时间窗口的测试。"""

import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from us_stock_agent import research_context
from us_stock_agent.evidence_analysis import validate_and_render_analysis
from us_stock_agent.market_data import YFinanceProvider

NOW = datetime(2026, 10, 12, 6, tzinfo=timezone.utc)


class TestResearchFramework(unittest.TestCase):
    """观点必须有作者、时间、来源，不能代替证券事实。"""

    def config(self):
        """构造与真实账号无关的测试输入。"""
        return {'authors':[{'id':'x:sample','platform':'x','name':'样本作者','handle':'sample',
                            'profile_url':'https://x.com/sample'}],
                'posts':[{'author_id':'x:sample','url':'https://x.com/sample/status/12345',
                          'published_at':'2026-10-11T08:00:00Z','symbols':['SPCX'],
                          'text':'样本观点：需核验经营情况。','content_kind':'user_transcription'}]}

    def test_unconfigured_opinions_are_explicitly_missing(self):
        """没有账号时不能制造博主共识。"""
        result, warnings = research_context.collect_social_opinions(['SPCX'], env={'SOCIAL_OPINIONS_JSON':'{"authors":[],"posts":[]}'}, now=NOW)
        self.assertEqual(result['SPCX']['status'],'not_configured')
        self.assertEqual(result['SPCX']['posts'],[])

    def test_transcription_preserves_author_and_unverified_status(self):
        """手工转录只能表示输入提供了原文，不能表示已在线核验。"""
        result, _ = research_context.collect_social_opinions(['SPCX'],env={'SOCIAL_OPINIONS_JSON':json.dumps(self.config())},now=NOW)
        post = result['SPCX']['posts'][0]
        self.assertEqual(post['author']['name'],'样本作者')
        self.assertEqual(post['verification'],'user_provided_not_independently_verified')

    def test_unknown_author_is_rejected(self):
        """不能把非关注名单的观点冒充指定博主。"""
        config=self.config(); config['posts'][0]['author_id']='x:someone_else'
        with self.assertRaisesRegex(ValueError,'作者'):
            research_context.collect_social_opinions(['SPCX'],env={'SOCIAL_OPINIONS_JSON':json.dumps(config)},now=NOW)

    def test_future_posts_cannot_enter_current_analysis(self):
        """防止未来日期内容进入本次分析。"""
        config=self.config(); config['posts'][0]['published_at']='2026-10-13T08:00:00Z'
        result, warnings=research_context.collect_social_opinions(['SPCX'],env={'SOCIAL_OPINIONS_JSON':json.dumps(config)},now=NOW)
        self.assertEqual(result['SPCX']['posts'],[])
        self.assertTrue(warnings)

    def test_old_post_is_excluded_from_recent_opinions(self):
        """过期观点不能包装成本周观点。"""
        config=self.config(); config['posts'][0]['published_at']='2026-08-01T08:00:00Z'
        result, _=research_context.collect_social_opinions(['SPCX'],env={'SOCIAL_OPINIONS_JSON':json.dumps(config)},now=NOW)
        self.assertEqual(result['SPCX']['posts'],[])

    def test_platform_domain_mismatch_is_rejected(self):
        """伪造平台链接必须显式报错。"""
        config=self.config(); config['posts'][0]['url']='https://example.com/post'
        with self.assertRaisesRegex(ValueError,'链接|平台'):
            research_context.collect_social_opinions(['SPCX'],env={'SOCIAL_OPINIONS_JSON':json.dumps(config)},now=NOW)

    def test_framework_covers_six_dimensions(self):
        """框架显式区分事实、推断和社交意见。"""
        self.assertEqual(set(research_context.DIMENSIONS), {'market','fundamentals','catalysts','technical','social','portfolio'})

    def test_financial_period_date_is_not_shifted_to_previous_new_york_day(self):
        """财务报告期是日历日期，不能按交易所时区减一天。"""
        provider=YFinanceProvider.__new__(YFinanceProvider)
        provider.yf=SimpleNamespace(Ticker=lambda symbol:SimpleNamespace(info={'symbol':'SPCX','mostRecentQuarter':1782777600}))
        self.assertEqual(provider.fetch_company_facts('SPCX')['report_period_end'],'2026-06-30')

    def test_v2_rejects_missing_dimensions(self):
        """新版报告不能只换标题而仍输出旧的技术套话。"""
        evidence={'SPCX':{'framework':{'id':'SPCX:framework','version':'evidence_research_v2'},'social':{'posts':[]}}}
        item={'symbol':'SPCX','thesis':'待核验','counter_evidence':'未提供','uncertainty':'样本不足',
              'next_check':'核对数据','evidence_ids':['SPCX:framework']}
        with self.assertRaisesRegex(ValueError,'六维|dimensions'):
            validate_and_render_analysis(json.dumps({'positions':[item]}),evidence)

    def test_v2_renders_each_author_with_source_link(self):
        """博主观点必须逐条复核，不能合并成无来源的看多共识。"""
        evidence={'SPCX':{'framework':{'id':'SPCX:framework','version':'evidence_research_v2'},
                         'social':{'id':'SPCX:social','posts':[{'id':'SPCX:social:post:0','author':{'name':'样本作者'},
                                   'text':'观点待验证','url':'https://x.com/sample/status/12345','published_at':'2026-10-11T08:00:00Z',
                                   'verification':'original_page_read_claims_unverified'}]}}}
        item={'symbol':'SPCX','thesis':'待核验','counter_evidence':'未提供','uncertainty':'样本不足','next_check':'核对数据',
              'evidence_ids':['SPCX:framework'], 'dimensions':{key:'证据不足，需核验' for key in research_context.DIMENSIONS},
              'opinion_reviews':[{'source_id':'SPCX:social:post:0','stance':'待核实','reason':'需要独立证据'}]}
        text=validate_and_render_analysis(json.dumps({'positions':[item]}),evidence)
        self.assertIn('样本作者',text)
        self.assertIn('https://x.com/sample/status/12345',text)
        self.assertIn('待核实',text)


if __name__ == '__main__':
    unittest.main()
