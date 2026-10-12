"""新闻线索匹配与部分服务故障的回归测试。"""

import unittest
from us_stock_agent.news import _infer_risk_flag, MultiNewsProvider, NewsItem


class BadProvider:
    """模拟一个失败新闻源。"""
    provider_name = 'bad'

    def fetch_news(self, symbols):
        """模拟接口超时。"""
        raise TimeoutError('down')


class GoodProvider:
    """模拟仍可用的新闻源。"""
    provider_name = 'good'

    def fetch_news(self, symbols):
        """返回来源明确的有效线索。"""
        return {symbol:[NewsItem(symbol,'earnings report','test',url='https://example.com')] for symbol in symbols}


class TestNewsIntegrity(unittest.TestCase):
    """关键词不能截取无关单词；单源失败不能丢失其他源。"""

    def test_sector_is_not_sec_investigation(self):
        """sector 中的 sec 子串不表示监管调查。"""
        self.assertIsNone(_infer_risk_flag('Technology sector second quarter update'))

    def test_one_failed_provider_does_not_drop_good_results(self):
        """接口故障必须保留其他源的结果并记录降级。"""
        provider = MultiNewsProvider([BadProvider(),GoodProvider()])
        self.assertEqual(len(provider.fetch_news(['SPCX'])['SPCX']),1)
        self.assertTrue(provider.warnings)


if __name__ == '__main__':
    unittest.main()
