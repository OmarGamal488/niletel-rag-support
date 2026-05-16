ADSL Legacy Troubleshooting Guide

دليل حل مشاكل الـ ADSL القديم

يا فندم، عندنا لسه عدد كبير من العملاء على خطوط ADSL خصوصاً في المحافظات اللي لسه ما عندهاش FTTH كامل. لما العميل يبلغ إن النت بطيء أو مفصول، اتبع الخطوات دي:

أولاً: اطلب رقم الخط واتأكد إن العميل على باقة ADSL مش fiber في الـ CRM. كتير عملاء بيتصلوا وهما متحولين لـ FTTH من فترة وما يعرفوش.

ثانياً: اعمل line test من الـ DSLAM:
- شيك على الـ sync rate (لازم يكون أعلى من 4 Mbps للباقات 8 ميجا)
- SNR margin لازم يكون أعلى من 6 dB
- attenuation أقل من 50 dB
- لو الـ stats سيئة، المشكلة في كابل الـ copper من الـ exchange للعميل

ثالثاً: لو الـ line stats كويسة بس السرعة بطيئة:
- اطلب من العميل يعمل speed test من جهاز متوصل بكابل مباشرة بالـ router
- اتأكد إنه مش متوصل بـ WiFi 2.4GHz بس
- شيك على الـ usage logs، ممكن يكون تخطى الـ Fair Usage Policy

رابعاً: الإصلاحات اللي ممكن نعملها remote:
- profile change من interleaved لـ fast path (يحسن latency بس يقلل stability)
- DSLAM port reset
- تغيير الـ DSLAM card لو في cross-talk من خطوط تانية

لو محتاج field visit:
ارفع P3 ticket واطلب من فريق الـ outside plant يفحص الـ junction box وكابل الـ drop wire. الوقت المتوقع 24-48 ساعة في القاهرة، و72 ساعة في المحافظات.

نصيحة لـ retention:
ADSL technology بقت قديمة. لو العميل في منطقة فيها FTTH coverage، اعرض عليه upgrade بـ 50% خصم على installation. النسبة عندنا 73% بيوافقوا لما العرض يتقدم في وقت المشكلة.

Last Updated: February 2026 | Network Operations Department
