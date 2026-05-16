Static IP Allocation for Business Customers

تخصيص الـ Static IPs للعملاء التجاريين

يا فندم، طلب Static IPs من العملاء البيزنس بقى متكرر جداً مع انتشار VPN, remote work, hosted servers. الـ allocation policy عندنا صارمة لأن الـ IPv4 pool محدود ومرتبط بـ APNIC quota.

الـ Eligibility:
- لازم العميل عنده Business contract (مش consumer)
- لازم Commercial Register ساري
- مطلوب technical justification مكتوبة
- ممنوع لـ illegal hosting (gambling, adult content, etc.)

Allocation Tiers:

**Single Static IP (/32)**:
- 50 جنيه/شهر إضافي على الـ baseline
- Purpose: remote access (VPN endpoint), CCTV, single web server
- Approval: 24 ساعة، self-service من Self-Care Business Portal

**Small Block (/30)**:
- 4 IPs (2 usable)
- 150 جنيه/شهر
- Purpose: small mail server + backup
- Approval: 48 ساعة، AM signature

**Medium Block (/29)**:
- 8 IPs (6 usable)
- 350 جنيه/شهر
- Purpose: production web + mail + DNS infrastructure
- Approval: 5 أيام عمل، technical review + AM + Capacity Planning

**Large Block (/28 or larger)**:
- 16+ IPs
- Custom pricing
- Purpose: hosting providers, ISPs, large enterprises
- Approval: 2-4 أسابيع، NTRA notification, APNIC justification doc

Required Documentation:
1. **Network Diagram** — current + planned topology
2. **Application List** — كل service هياخد IP إيه
3. **Growth Forecast** — 3-year projection
4. **Reverse DNS Requirements** — لو الـ mail servers محتاجة PTR records

The Process:
1. Customer submits request via portal أو AM
2. NileTel verifies eligibility + checks block availability
3. لو > /29: technical review meeting (30 دقيقة virtual call)
4. Issuance: IPs بتظهر في الـ CPE config، PTR records بتتعمل خلال 48 ساعة
5. Customer signs Acceptable Use Policy + technical handover

Reclamation Policy:
- IPs that are unused for 6 months: warning notice
- 9 months unused: reclamation + refund للشهر الأخير
- العميل يقدر يطلب exception لو في business reason
- الـ NTRA بتراجعنا سنوياً على utilization rate

Common Misconceptions:
- "أنا عايز IP ثابت عشان النت يبقى أسرع" → لا، الـ static IP ما يؤثرش على السرعة
- "محتاج IP عشان WhatsApp Business يشتغل" → لا، WhatsApp ما يحتاجش IP ثابت
- "Static IP بيخلي الـ port forwarding يشتغل" → جزئياً، الـ static IP ضروري لـ inbound services بس مش كافي وحده

Technical Implementation:
- الـ static IPs بتتـ delivered عبر:
  - **FTTH**: routed على الـ CPE (Huawei OptiXstar) كـ VLAN tag مخصص
  - **DIA**: BGP announcement لو الـ customer عنده AS رقم
  - **5G FWA**: tunneled عبر GRE
- العميل لازم يـ configure الـ default route + NAT (لو محتاج)

NAT vs Static Public IPs:
كل عملاء الـ consumer وراء CG-NAT (Carrier-Grade NAT). الـ business customers في options:
- 1:1 NAT (default للـ Silver tier)
- Multiple public IPs (Gold+)
- BYOIP (Bring Your Own IP) للـ enterprises عندهم AS مسجل

Common Issues:
- "الـ IP اتغير بدون ما أعرف" → ده ما بيحصلش مع Static IP طول العقد ساري. لو حصل: investigation فوري + apology + service credit
- "محتاج المزيد من الـ IPs مفاجئ" → emergency allocation متاحة في 24 ساعة بضمان temporary، capacity planning بياخد لـ 5 أيام للـ permanent

Last Updated: March 2026 | Network Engineering & Capacity Planning
