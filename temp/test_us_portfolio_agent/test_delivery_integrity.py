"""邮件发送确认、图表降级和失败告警的回归测试。"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from us_stock_agent.llm_enhancer import LLMEnhanceResult

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('send_report_test', ROOT / 'scripts/send_email_report.py')
sender = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sender)


class TestDeliveryIntegrity(unittest.TestCase):
    """可选图片失败不能吞掉邮件；跳过发送不能作为送达。"""

    def args(self):
        """模拟工作流使用的严格发送参数。"""
        return SimpleNamespace(report_file='dummy',subject=None,require_sent=True,result_file=None)

    def test_missing_smtp_is_failure_when_delivery_required(self):
        """生产 workflow 缺 SMTP 时不得写成功 marker。"""
        with patch.object(sender,'parse_args',return_value=self.args()), \
             patch.object(sender,'_load_report',return_value={'ok':True,'data':{'report_markdown':'facts'}}), \
             patch.object(sender,'enhance_report_markdown_for_email',return_value=LLMEnhanceResult('facts',False,True,'missing')), \
             patch.object(sender,'_build_chart_images',return_value=[]), \
             patch.object(sender,'send_email_markdown',return_value={'sent':False,'skipped':True,'reason':'smtp_not_configured'}):
            self.assertEqual(sender.main(),2)

    def test_optional_chart_failure_still_sends_core_report(self):
        """图表异常时发送正文并显式提示缺图。"""
        with patch.object(sender,'parse_args',return_value=self.args()), \
             patch.object(sender,'_load_report',return_value={'ok':True,'data':{'report_markdown':'facts'}}), \
             patch.object(sender,'enhance_report_markdown_for_email',return_value=LLMEnhanceResult('facts',False,True,'missing')), \
             patch.object(sender,'_build_chart_images',side_effect=RuntimeError('chart failed')), \
             patch.object(sender,'send_email_markdown',return_value={'sent':True,'skipped':False}) as send:
            self.assertEqual(sender.main(),0)
            self.assertIn('图表',send.call_args.args[0])

    def test_embedded_history_never_refetches_market_data(self):
        """发送阶段从 JSON 复用本次行情，不再次联网换价格。"""
        report={'data':{'symbols':['SPCX'],'chart_history':{'SPCX':[
            {'date':'2026-10-09','open':165.34,'high':166.38,'low':160.61,'close':162.57,'volume':1000}]}}}
        with patch.dict('os.environ',{'EMAIL_INCLUDE_CHARTS':'true'}), \
             patch.object(sender,'YFinanceProvider',side_effect=AssertionError('unexpected refetch')):
            self.assertEqual(len(sender._build_chart_images(report)),1)


if __name__ == '__main__':
    unittest.main()
