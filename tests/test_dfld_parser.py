"""Parser contract tests use synthetic HTML, not copies of DFLD pages."""
import unittest
from datetime import date
from scripts.fetch_dfld import parse_weather, parse_airport, changes


class DfldParserTests(unittest.TestCase):
    def test_unknown_bins_and_changed_interval(self):
        page = '<tr><td>29.10.2026:</td><td>' + ''.join([
            '<img title="09:30 - 10:00: BR25">', '<img title="10:00 - 10:30: BR07">',
            '<img title="10:00 - 10:30: 0&deg;">', '<img title="11:00 - 11:30: BR25">']) + '</td></tr>'
        bins = parse_weather(page, date(2026, 10, 29))
        self.assertIsNone(bins[0]['operatingDirection'])
        self.assertEqual(bins[20]['windDirectionDeg'], 0)
        self.assertEqual(changes(bins), [{'sourceTime':'10:00','sourceEndTime':'10:30','from':'25','to':'07'}])
        with self.assertRaises(ValueError):
            parse_weather(page, date(2026, 10, 28))

    def test_duplicate_and_non_halfhour_rejected(self):
        for titles in [('10:00 - 10:30: BR07',)*2, ('10:00 - 10:45: BR25',)]:
            page = '<tr><td>29.10.2026:</td><td>' + ''.join(f'<img title="{t}">' for t in titles) + '</td></tr>'
            with self.assertRaises(ValueError):
                parse_weather(page,date(2026,10,29))

    def test_movement_reconciliation_and_unknown_runway(self):
        def movement(clock,kind,runway):
            return '<tr>'+''.join(f'<td>{c}</td>' for c in [clock,kind,'','','','','',runway])+'</tr>'
        detail = movement('05:30:00','&#xe916;','18')+movement('06:12:00','&#xe917;','07L')+movement('06:40:00','&#xe916;','')
        page = '<h2>Einzelauflistung</h2><table>'+detail+'<tr><td>Summe: 3</td></tr></table><h2>Pisten Belegung</h2><table><tr><th colspan="2">07L</th><th colspan="2">18</th><th colspan="2">&#xe918;</th></tr><tr>'+''.join(f'<td>{x}</td>' for x in ['&Sigma;',0,1,1,0,1,0,3])+'</tr></table>'
        hours,runways,total = parse_airport(page)
        self.assertEqual(total,3)
        self.assertEqual(hours[5]['rwy18Departures'],1)
        self.assertEqual(hours[6]['arrivals07'],1)
        self.assertIsNone(hours[0]['rwy18Closed'])
        self.assertEqual(runways[-1]['departures'],1)
        with self.assertRaises(ValueError): parse_airport(page.replace('Summe: 3','Summe: 4'))
        with self.assertRaises(ValueError): parse_airport(page.replace('&#xe916;','?'))


if __name__ == '__main__': unittest.main()
