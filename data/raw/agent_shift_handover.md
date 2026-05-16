Customer Care Agent — Shift Handover Checklist

قائمة تسليم الـ shift لوكلاء خدمة العملاء

يا فندم، الـ NileTel Customer Care Center بيشتغل 24/7 على 3 shifts (morning, afternoon, night). الـ handover بين الـ shifts لازم يكون منظم عشان الـ open tickets ما تضيع، والعميل ما يضطرش يكرر شكواه لكل agent جديد.

Shift Schedule:
- **Morning**: 06:00 - 14:00 (peak hours, max staffing)
- **Afternoon**: 14:00 - 22:00 (peak hours)
- **Night**: 22:00 - 06:00 (minimum staffing, on-call escalation)

15 Minutes Before End of Shift:
1. **اقفل الـ tickets اللي ممكن تتقفل** — لو في solution clear، agree it مع العميل واقفلها قبل ما تسلم
2. **حدّث الـ status فيي tickets pending** — اكتب آخر updates في الـ ticket comments
3. **اعمل review للـ unanswered queue** — لو في tickets > 30 min بدون reply، اعمل initial response

Handover Template:
لكل ticket مش متقفل، اكتب في الـ ticket:
```
[HANDOVER - <shift name> @ <time>]
Customer state: [مزاجه - calm / frustrated / angry]
Last action taken: <what you did>
Next steps: <what should be done>
Time-sensitive: <yes/no, deadline if yes>
Escalation status: <Tier 1/2/3>
Customer expectation: <what you told them to expect>
Special notes: <anything relevant>
```

Examples:

```
[HANDOVER - Morning @ 13:55]
Customer state: frustrated بس reasonable
Last action: opened P2 ticket for FTTH down, technician dispatched
Next steps: call customer in 2 hours to confirm technician arrival
Time-sensitive: yes, customer expects callback by 16:00
Escalation: Level 1 (handled normally)
Customer expectation: technician at his location by 17:00
Notes: عنده meeting مهمة 18:00، لو technician اتأخر اعرض MiFi backup مجاناً
```

```
[HANDOVER - Afternoon @ 21:50]
Customer state: hostile, threatening to file NTRA complaint
Last action: offered 200 EGP goodwill credit, customer rejected
Next steps: escalate to retention specialist tomorrow morning
Time-sensitive: no
Escalation: Level 2 needed
Customer expectation: callback from senior agent بكره
Notes: في billing dispute open لـ 18 days، خرجت الـ NTRA SLA، compensation lazem
```

Pending Items Pickup List:
Incoming shift agent بيـ start بـ:
1. ادخل الـ unified dashboard → "Handed Over Tickets" filter
2. اقرأ آخر comment لكل ticket
3. شيك الـ time-sensitive flag → prioritize عليها
4. لو في > 5 handed-over tickets، اطلب من الـ supervisor support إضافية

Critical Categories Always Highlighted:
- VIP / Golden customers (red flag in CRM)
- NTRA-escalated complaints
- Service outages affecting clusters
- Compliance issues (data privacy, billing legal)
- Fraud-related tickets
- Customer threatened legal action

Shift Lead Responsibilities:
- Final review لكل tickets المسلمة قبل end of shift
- Brief الـ incoming Shift Lead عن major incidents
- Sign off على الـ handover log

Communication Channels:
- **Slack #cc-handover** — quick notes between agents
- **Confluence — Daily Shift Log** — written record كل shift
- **Phone briefing** — لو في critical incident، 5-min call between shift leads

Quality Checks:
الـ team supervisor بـ random sampling 5% من الـ handovers اليومية:
- Was the handover note complete?
- Did the next agent pick it up within SLA?
- Was the customer's perception consistent across shifts?
- Score: 0-10، target 8.5+

Tools Available:
- **Customer 360 dashboard** — كل التاريخ مع العميل في view واحد
- **Sentiment analyzer** — يكشف الـ "anger level" تلقائي من آخر مكالمات
- **Translation tool** — للعملاء اللي بيتكلموا English أو Arabic بس
- **Knowledge base search** — instant answers من docs زي ده

Common Mistakes:
- ❌ Marking tickets "resolved" قبل ما العميل يأكد
- ❌ Handover note ناقصة أو vague
- ❌ Forgetting to update customer's preferred language
- ❌ Not flagging time-sensitive items
- ❌ Leaving angry customer to next shift without warning

Last Updated: April 2026 | Customer Care Operations
