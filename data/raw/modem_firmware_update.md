Modem & Router Firmware Update Guide

دليل تحديث الـ firmware للـ modems والـ routers

يا فندم، 28% من شكاوى الـ FTTH اللي بتتقفل بـ "no fault found" بترجع أصلاً لـ firmware قديم. لما العميل يبلغ مشكلة connectivity أو speed، شيك على الـ firmware version قبل أي escalation.

الـ Supported Devices:
- **Huawei HG8245H** — most common، supports auto-update من 2024
- **Huawei OptiXstar EG8245W6** — Wi-Fi 6، new fleet من 2025
- **ZTE F660** — legacy، manual update only
- **ZTE ZXHN H168N** — VDSL legacy
- **Nokia G-2425G-A** — premium tier (corporate + VIP)
- **TP-Link Archer C7** — customer-owned (BYOD)

التحقق من الـ Current Firmware Version:
1. ارجع للـ CRM → Customer Profile → Connected Devices
2. الـ ACS (TR-069) بيرجع الـ version تلقائي لو الجهاز online
3. لو الجهاز offline: اطلب من العميل يدخل web UI (192.168.1.1) → Status → System Info

الـ Update Methods:

**Method 1: ACS Push (الأفضل)**:
- نظام TR-069 بيدفع الـ update remotely
- بياخد 5-10 دقايق
- الجهاز بيـ reboot مرة واحدة
- ما يحتاجش العميل يعمل أي حاجة
- الـ scheduling default: بين 3 و 5 صباحاً

**Method 2: Customer-Initiated**:
- العميل يفتح web UI
- Maintenance → Firmware Upgrade
- بيـ pull من NileTel firmware server (TR-069 URL)
- مدة 5-15 دقيقة

**Method 3: Manual (للحالات القديمة)**:
- نطلب من العميل firmware file specific
- بنرسله لينك للـ NileTel CDN
- بيرفع الـ file من web UI

Pre-Update Checks:
1. شيك الـ battery backup لو فيه (للأجهزة الـ FTTH)
2. تأكد من signal strength (RX power أعلى من -25 dBm)
3. warn العميل: "هيحصل reboot واحد، النت هيرجع في 5 دقايق"
4. خد screenshot لـ current config (لو هيتعمل factory reset مع الـ update، رجّعها بعدين)

Known Issues per Device:

**Huawei HG8245H**:
- Firmware V3R017C10S210 → عنده memory leak بعد 14 يوم uptime. Update لـ V3R019 أو أحدث.
- لو الـ device في حالة boot loop بعد الـ update → الـ rollback firmware موجود في الـ ACS

**ZTE F660**:
- ما يقبلش update remote، لازم manual أو device replacement
- الفرع الأقرب يقدم replacement بـ 100 جنيه لو الـ device حر vs upgrade الباقة

**Nokia G-2425G-A**:
- يحتاج reboot بعد الـ update عشان الـ Wi-Fi profile يـ apply
- بعض الـ firmware versions بتـ reset الـ WPA password → تأكد من العميل بعد الـ update

Post-Update Verification:
1. اطلب من العميل يشغل speed test (Ookla)
2. شيك الـ signal stats في الـ ACS
3. اتأكد من الـ Wi-Fi password (لو اتغير)
4. close الـ ticket بـ resolution code "FIRMWARE_UPDATE"

Mass Update Campaigns:
كل quarter، الـ engineering team بتعمل mass push على devices مع firmware حرج. الـ communication:
- 7 أيام قبل: SMS عام
- 3 أيام قبل: email + in-app notification
- يوم الـ update: SMS تذكير
- الـ window: 2-5 AM

Last Updated: January 2026 | Network Operations Engineering
