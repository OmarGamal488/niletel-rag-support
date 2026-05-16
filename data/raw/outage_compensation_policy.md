Network Outage Compensation Policy

سياسة التعويضات في حالة انقطاع الخدمة

يا فندم، الانقطاعات بتحصل — sometimes due to fiber cut، power failure، أو DDoS attack. الأهم إن العميل يحس إن في عدالة في الـ compensation. عندنا automated policy عشان نضمن الـ fairness.

Outage Severity Classification:

**P1 — Major Outage (≥1000 users affected)**:
- Examples: governorate-wide FTTH down, mobile network outage في مدينة
- NTRA notification mandatory في 30 دقيقة
- Public communication via NileTel app + social media + SMS

**P2 — Significant (100-999 users)**:
- Examples: cell tower failure, regional fiber cut
- Internal escalation: NOC L2 + COO notification
- Customer SMS notification

**P3 — Local (10-99 users)**:
- Examples: street-level fiber damage, single DSLAM فاشل
- Field dispatch automatic
- Direct customer call

**P4 — Individual (1-9 users)**:
- Examples: CPE failure, drop wire damage
- Handle via standard ticket flow

Compensation Formula (Automatic):

```
Compensation = (Monthly Bill / 30) × Days of Outage × Multiplier

Multiplier:
- 1x for outage 4-24 ساعة
- 1.5x for outage 24-72 ساعة
- 2x for outage > 72 ساعة
- 3x for repeat outage (same location, 3+ في 90 يوم)

Plus:
- 100 جنيه goodwill credit لـ outage > 48 ساعة
- Free service month لـ outage > 7 أيام
```

How It's Applied:
- النظام بيحسب تلقائي من الـ network monitoring data (لما الـ device offline timestamp مسجلة)
- بيـ apply كـ credit في فاتورة الشهر التالي
- لا يحتاج العميل يطلب — preemptive credit
- SMS بيتبعت: "يا فندم، اعتذرنا عن الانقطاع. تم إضافة XX جنيه credit في حسابك."

Special Cases:

**Force Majeure**:
لو الانقطاع بسبب:
- Natural disaster (زلازل، فيضانات)
- Government order (lawful intercept blackout)
- War / civil unrest
- Power grid failure > 24 ساعة على national level

→ Compensation reduced لـ 50%. مش 0% لأن الـ NTRA ما تقبلش full waiver.

**Customer-Caused Outage**:
- Cable cut من العميل
- Equipment misuse
- Tampering with installation
- Unpaid balance leading to suspension

→ No compensation. توضيح للعميل بشكل واضح + professional.

**Planned Maintenance**:
- لازم notification 72 ساعة مسبقاً بـ SMS + email + in-app
- Max duration 4 ساعات
- Between 12 AM - 5 AM local time
- لو فاتت الـ duration المعلنة → النظام بيتعامل معاها كـ unplanned outage

VIP / Corporate Compensation:
الـ SLA contracts مع الـ corporate clients بتعمل override للـ formula اللي فوق:
- Platinum: 10% monthly fee credit لكل ساعة of downtime
- Gold: 5% per hour
- Silver: 2% per hour
- Cap: 100% (شهر مجاناً maximum)

Repeat Offenders:
لو الـ region فيها 3+ outages في 90 يوم:
- مراجعة infrastructure من Engineering
- يقدم لكل عميل في الـ region: free month + plan downgrade rebate (5% خصم لمدة سنة)
- Public apology عبر local press

Communication Templates:

"يا فندم، اعتذرنا عن انقطاع الخدمة من [time] إلى [time]. السبب كان [reason]. تم إضافة [amount] جنيه credit لحسابك."

"As-salamu alaykum, we apologize for the service interruption between [time] and [time]. The cause was [reason]. A credit of [amount] EGP has been applied to your account."

"يا فندم، الخدمة شغالة دلوقتي. لو لسه عندك مشكلة شخصية، اتصل بينا فوراً. شكراً لصبرك."

Public Statement Approval Chain:
لـ outages > 10,000 users:
- النص يتكتب من PR Team
- Review من Legal (compliance with NTRA)
- Final approval من CCO
- Publish في 30 دقيقة من بداية الانقطاع

Last Updated: March 2026 | Network Operations & Customer Care
