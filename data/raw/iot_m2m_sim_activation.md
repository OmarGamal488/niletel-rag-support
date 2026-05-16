IoT / M2M SIM Activation Guide

دليل تفعيل الـ IoT / M2M SIMs

يا فندم، عندنا قسم IoT بينمو بسرعة كبيرة — العميل المصري بقى يحتاج SIMs لـ smart meters، GPS trackers، POS machines، vending machines، الخ. الـ SIM ده مختلف عن الـ consumer SIM في كذا حاجة جوهرية.

الفروق الأساسية:
1. **No voice / SMS by default** — data-only، إلا لو العميل طلب SMS مفعل (للـ alerts)
2. **APN مخصص** — مش "internet.niletel.com.eg" زي الـ consumer، بقى "iot.niletel.com.eg" مع private IP pool
3. **No KYC fingerprint per SIM** — الـ corporate account هو المسؤول، مش الـ end device
4. **Bulk activation** — لازم بـ batches 50+ SIMs
5. **Lifetime activation** — مش بيتعلق لو ما استخدمش (الـ consumer SIM بيتعلق بعد 90 يوم idle)

الباقات الـ IoT المتاحة:
- **Micro-IoT**: 100 MB/شهر، 30 جنيه. مناسب لـ smart meters، sensors بسيطة
- **Standard-IoT**: 1 GB/شهر، 80 جنيه. مناسب لـ POS, trackers
- **Heavy-IoT**: 10 GB/شهر، 300 جنيه. مناسب لـ surveillance cameras, in-vehicle
- **Custom pool**: shared pool عبر كل الـ fleet، pricing بالميجا بعد negotiation

Activation Process (Bulk):
1. العميل بيقدم CSV file فيه: ICCID, IMSI, device_serial, deployment_address
2. الـ IoT Provisioning Portal بيعمل validate على الـ ICCIDs
3. بنفعّل كلهم في 24 ساعة على الـ APN المتفق عليه
4. الـ activation confirmation بترجع API webhook للـ customer's NMS

Lifecycle Management:
- **Active**: working normally, data flowing
- **Inactive**: in stock, not deployed yet
- **Suspended**: deployed but temporarily disabled (e.g., theft suspected)
- **Deactivated**: end-of-life, can't reactivate

Static IPs للـ IoT:
- /30 per device بـ 50 جنيه/شهر إضافي
- /29 per device بـ 150 جنيه/شهر
- لازم العميل يثبت إن الـ device بيحتاج reachability من خارج الشبكة

Common IoT Use Cases عند NileTel customers:
- **Smart electricity meters** — Egyptian Electricity Holding Company, 850K SIMs
- **Vehicle tracking** — fleet management شركات النقل
- **POS machines** — مطاعم، سوبر ماركتس
- **ATM connectivity** — backup link لما الـ wired link يفصل
- **Agriculture sensors** — soil moisture، weather stations في الدلتا

Troubleshooting شائع:
- "الـ SIM مش بيعمل register" → شيك الـ IMEI lock، بعض الـ devices مقفولة على network code محدد
- "Connectivity intermittent" → شوف الـ signal strength في الـ location، ممكن تحتاج external antenna
- "Bill عالية فجأة" → شيك لو الـ device اخترق، أو لو فيه firmware update غير متوقع

Last Updated: February 2026 | IoT & Enterprise Services
