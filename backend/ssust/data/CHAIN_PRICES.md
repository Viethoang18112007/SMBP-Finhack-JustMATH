# Chain prices

`chain_prices.json` gives one typical meal price range per restaurant chain, taken from
published prices: the chain's own menu, or a news report of its prices. The range is used
for every branch on the map whose name contains one of the chain's names, so ~260 places
get a real price from 20 records.

A chain price is less exact than a verified dish price (`verified_prices.json`): a branch
can charge a little more or less, and promotions change. So the map always says
"(chain price)", and a verified price for a branch always wins over its chain price.

## Record format

```json
{
  "chains": [
    {
      "chain": "<the chain's name>",
      "names": ["<every name it appears under on the map, English and Chinese>"],
      "what": "<what the range covers, e.g. Lunch sets>",
      "low_cents": <cheapest typical meal, whole cents: HK$29 is 2900>,
      "high_cents": <dearest typical meal, whole cents>,
      "sources": ["<menu URL or news URL, or: visited in person>"],
      "checked_on": "<the date you read the sources, YYYY-MM-DD>",
      "needs_check": <true until someone has seen the prices in a shop, then false>,
      "note": "<optional: the prices you read, so the next person can re-check them>"
    }
  ]
}
```

Rules (checked at start-up; a bad record is listed in the server log and not used):

- Every field above is required except `note`. No other fields.
- `low_cents` and `high_cents` are whole numbers above 0, and low is not above high.
- `names` are matched with case, accents, spaces and punctuation ignored, anywhere in the
  place's name: "McDonald's" matches "麥當勞 McDonald's (HKUST)". Each name needs at least 2
  letters or digits. If two chains match, the longer name wins.
- Use a typical meal for one person (a set with a drink), not a one-off promotion, not a
  shared meal for two.
- Set `needs_check` to `false` only after someone has seen the prices in a branch or on the
  chain's own current menu. The map adds "not yet checked in a shop" while it is `true`.

Check the file after editing it:

```sh
python tools/check_prices.py
```

## The shipped records (all still need checking)

| Chain | Range | Read from |
| --- | --- | --- |
| McDonald's | HK$29 to HK$46 | SCMP report of the official price list |
| Café de Coral | HK$33 to HK$57 | Sing Tao report of set prices, one customer review |
| Maxim's MX | HK$33 to HK$49 | Sing Tao reports (promotion prices) |
| TamJai SamGor / TamJai Yunnan | HK$38 to HK$55 | etnet report, one customer review |
| Starbucks | HK$35 to HK$52 | Starbucks menu (Sep 2026) on cso.hkust.edu.hk, drinks only |
| Fairwood | HK$34 to HK$55 | Sing Tao report, one customer review |
| KFC | HK$23 to HK$45 | MoneyHero and HK01 reports (breakfast, rice bowls) |
| Pacific Coffee | HK$38 to HK$53 | foodpanda listing, drinks only |
| Zeppelin Hot Dog | HK$40 to HK$57 | Foodie article, OpenRice dish page |
| Subway | HK$39 to HK$65 | HKU outlet menu (2023), Subway HK catering menu (2024) |
| Pepper Lunch | HK$66 to HK$73 | menu price site (not official) |
| Genki Sushi | HK$59 to HK$90 | Genki Sushi lunch menu (May 2026), lunch only |
| Pizza Hut | HK$69 to HK$114 | HK01 report, plus 10% service charge |
| Gyu-Kaku | HK$69 to HK$159 | customer reviews, lunch only |
| Man Kee Cart Noodle | HK$40 to HK$60 | one customer review |
| Katoya | HK$40 to HK$60 | customer reviews (promotion price) |
| Loud Tea | HK$33 to HK$47 | foodpanda listing, drinks only |
| Jollibee | HK$40 to HK$55 | Jollibee press release (Nov 2026) |
| Pret A Manger | HK$28 to HK$56 | foodpanda listing, drinks extra |
| MOS Burger | HK$31 to HK$55 | customer reviews |

Chains on the map with no record yet (no usable price source found): E.Tea, HI TEA,
Fantastic Tea, Tong Kee Bao Dim, Grove, Pizza Box, Sushi Takeout, Sushi Express, On-Yasai.
Add them the same way after checking a menu or a shop.
