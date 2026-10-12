"""证据分析模式的事实保护和异常响应回归测试。"""

import json
import unittest
from unittest.mock import patch

from us_stock_agent.llm_enhancer import LLMConfig, enhance_report_markdown_for_email
from us_stock_agent.runner import run_report
from test_runner import FakeMarketProvider
from us_stock_agent.models import Holding, Portfolio


class Response:
    """模拟完整 SSE 响应。"""

    status_code = 200

    def __init__(self, text):
        """保存模型输出。"""
        self.text = text

    def iter_lines(self, **kwargs):
        """返回最终正文以及结束事件。"""
        return ['data: ' + json.dumps({'choices':[{'delta':{'content':self.text}}]}), 'data: [DONE]']


class TestEvidenceAnalysis(unittest.TestCase):
    """模型只能追加带引用的分析，不得替换原始财务结果。"""

    def run_analysis(self, item):
        """对最小证据包执行实际分析入口。"""
        report = {'data': {'evidence': {'SPCX': {'quote': {'id':'SPCX:quote', 'price':162.57},
                                                  'technical': {'id':'SPCX:technical'}, 'news':[]}}}}
        payload = {'positions':[item]}
        return enhance_report_markdown_for_email('# 原始事实\nSPCX 收盘 162.57 USD', report=report,
               config=LLMConfig(True,'dummy','https://api.deepseek.com','deepseek-flash','deepseek',max_tokens=8192),
               post=lambda *args, **kwargs: Response(json.dumps(payload, ensure_ascii=False)))

    def item(self):
        """提供带反向证据和不确定性的合法分析。"""
        return {'symbol':'SPCX', 'thesis':'价格走势需结合上市时间复核', 'counter_evidence':'历史较短，不能确认长期趋势',
                'uncertainty':'缺少财务与公告全文', 'next_check':'核对券商收盘口径', 'evidence_ids':['SPCX:quote']}

    def test_preserves_original_prices_and_adds_cited_analysis(self):
        """分析必须保留原始正文并能追溯引用。"""
        result = self.run_analysis(self.item())
        self.assertTrue(result.used)
        self.assertIn('# 原始事实\nSPCX 收盘 162.57 USD', result.markdown)
        self.assertIn('反向证据', result.markdown)
        self.assertIn('SPCX:quote', result.markdown)

    def test_unknown_citation_falls_back_to_facts(self):
        """编造证据 ID 时拒绝发布模型分析。"""
        item = self.item(); item['evidence_ids'] = ['SPCX:invented']
        result = self.run_analysis(item)
        self.assertFalse(result.used)
        self.assertIn('原始事实', result.markdown)

    def test_invented_price_falls_back_to_facts(self):
        """没有输入来源的数字不得进入分析。"""
        item = self.item(); item['thesis'] = '当前股价为 999.99 美元'
        result = self.run_analysis(item)
        self.assertFalse(result.used)

    def test_runner_exports_quote_and_chart_evidence(self):
        """JSON 应携带价格、动作与本次图表数据，供后续阶段复用。"""
        result = run_report(portfolio=Portfolio('USD',0,[Holding('NVDA',1)]), report_type='daily', market_provider=FakeMarketProvider())
        self.assertIn('evidence', result['data'])
        self.assertIn('chart_history', result['data'])
        self.assertIn('收盘', result['data']['report_markdown'])


if __name__ == '__main__':
    unittest.main()
