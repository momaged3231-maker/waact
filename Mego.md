# WAACT Official Operating Guide

هذا الملف هو دليل تشغيل السيستم رسميًا. الهدف منه أن تعرف ما المطلوب قبل التشغيل، كيف تشغل كل جزء، لماذا كل خطوة مهمة، وما الذي سيتوقف أو سيظل يعمل إذا لم تنفذ خطوة معينة.

## 1. السيستم بيعمل إيه؟

WAACT هو نظام WhatsApp CRM عربي لشركات الإنترنت ومقدمي خدمات ISP. النظام يستقبل رسائل العملاء من واتساب، يسجلها في قاعدة بيانات، يرد بالذكاء الاصطناعي، يحول الطلبات الصعبة للدعم، ويقدر يربط حالة الاشتراك من Radius/DMA ويجهز طلبات تغيير باسورد WiFi أو ينفذها تلقائيًا إذا بيانات الراوتر صحيحة.

المكونات الأساسية:

| المكون | مكانه | وظيفته | لو مش شغال هيحصل إيه |
|---|---|---|---|
| Backend | `backend` | API، Dashboard، قاعدة البيانات، AI، Radius، Router، التقارير | اللوحة كلها والردود التلقائية هتقف |
| WhatsApp Connector | `whatsapp-connector` | يفتح WhatsApp Web ويبعث الرسائل للـ Backend ويرسل ردود العملاء | واتساب مش هيستقبل أو يرد، لكن اللوحة والبيانات القديمة تشتغل |
| SQLite DB | `backend/waact.db` | تخزين العملاء، المحادثات، الحملات، الطلبات، الإعدادات التشغيلية | لو اتحذف هتبدأ بداتا فاضية |
| ChromaDB | حسب `CHROMA_PERSIST_DIR` | تخزين Knowledge Base للـ RAG | الذكاء الاصطناعي يشتغل بجودة أقل أو بدون معرفة الشركة |
| WhatsApp Session | `whatsapp-connector/session-data` | يحفظ تسجيل دخول واتساب بعد QR | لو اتحذف هتحتاج تعمل Scan QR من جديد |

## 2. أهم الصفحات بعد التبسيط

القائمة الرئيسية الآن معمولة للموظف والعميل بشكل أبسط:

| الصفحة | الرابط | الاستخدام |
|---|---|---|
| الرئيسية | `/` | ملخص سريع عن النظام والرسائل والطلبات |
| Inbox واتساب | `/whatsapp-chats` | المحادثات الحية، إرسال ردود، AI Assist، ملاحظات العميل |
| العملاء | `/customers` | بيانات العملاء وحالتهم وملاحظاتهم |
| الدعم والطلبات | `/support` | كل طلبات الدعم المفتوحة، Handoffs، طلبات WiFi اليدوية، المتابعات |
| الاشتراكات والراوترات | `/isp` | بحث سريع عن عميل لمعرفة الاشتراك، IP الحالي، وحالة الراوتر |
| الحملات | `/campaigns` | إرسال حملات واتساب مع Segments ومتغيرات |
| التقارير | `/reports` | تقارير يومية وأسبوعية وشهرية |

الصفحات التقنية لم تُحذف. موجودة تحت `Advanced / Admin` مثل Radius، Routers، Automation، Integrations، AI Health، Knowledge، Maintenance، Users، Audit.

## 3. المتطلبات قبل التشغيل الرسمي

| المطلوب | لماذا مهم؟ | لو مش موجود |
|---|---|---|
| Python 3.12 | تشغيل Backend FastAPI | السيرفر لن يعمل |
| Node.js 18 أو أحدث | تشغيل WhatsApp Connector | واتساب لن يعمل |
| Internet ثابت | WhatsApp Web والـ AI APIs | الرسائل أو AI ممكن يفصلوا |
| رقم واتساب مخصص للشركة | الربط الرسمي مع العملاء | هتضطر تستخدم رقم شخصي وهذا خطر تشغيلي |
| OpenAI API Key أو مزود AI شغال | الرد الذكي وRAG | الردود الذكية تتعطل أو تقل جودتها |
| بيانات Radius/DMA الحقيقية | معرفة حالة الاشتراك وIP العميل | صفحة الاشتراك تظل محدودة والتحويل للدعم يزيد |
| بيانات الراوتر/ACS/TR-069 أو API واضح | تغيير باسورد WiFi تلقائيًا | الطلب يتحول يدوي للدعم |
| Backup Plan | حماية قاعدة العملاء والمحادثات | فقدان الداتا عند تلف الجهاز أو نقل المشروع |

## 4. تثبيت Backend لأول مرة

افتح Terminal في مجلد المشروع:

```powershell
cd "C:\Users\moham\OneDrive\سطح المكتب\mmnn\waact\backend"
```

ثبت مكتبات Python:

```powershell
"C:\Users\moham\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
```

ماذا تفعل هذه الخطوة؟

تثبت FastAPI وUvicorn وSQLAlchemy وChromaDB وOpenAI وJinja وكل المكتبات التي يحتاجها السيرفر.

لو لم تنفذها:

السيرفر غالبًا سيظهر أخطاء مثل `ModuleNotFoundError` ولن يفتح Dashboard ولا API.

## 5. تثبيت WhatsApp Connector لأول مرة

افتح Terminal في مجلد connector:

```powershell
cd "C:\Users\moham\OneDrive\سطح المكتب\mmnn\waact\whatsapp-connector"
npm install
```

ماذا تفعل هذه الخطوة؟

تثبت `whatsapp-web.js` وExpress وAxios ومكتبات QR المطلوبة لربط واتساب.

لو لم تنفذها:

أمر `npm start` سيفشل، QR لن يظهر، والرسائل لن تدخل النظام.

## 6. إعداد `backend/.env`

الملف المهم للـ Backend هو:

```text
backend/.env
```

ابدأ من `backend/.env.example`، لكن لا تنشر القيم السرية لأي شخص.

الإعدادات الأساسية:

| المتغير | مثال | بيعمل إيه؟ | لو غلط أو فاضي |
|---|---|---|---|
| `APP_MODE` | `isp` | يخلي الواجهة مبسطة لموظف ISP | لو غير موجود سيستخدم `isp` تلقائيًا |
| `APP_URL` | `http://localhost:8000` | رابط لوحة التحكم والـ API | الروابط الداخلية أو التنبيهات ممكن تكون غلط |
| `SECRET_KEY` | قيمة طويلة عشوائية | توقيع جلسات الدخول | لو القيمة الافتراضية بقيت في الإنتاج فده خطر أمني |
| `DEBUG` | `false` | يمنع ظهور تفاصيل الأخطاء للمستخدم | لو `true` في الإنتاج ممكن يكشف تفاصيل حساسة |
| `AUTH_ENABLED` | `true` | يطلب Login للوحة | لو `false` أي شخص داخل الشبكة يقدر يفتح اللوحة |
| `AUTH_USERNAME` | `admin` | أول اسم مستخدم | بدون Auth مش مهم، مع Auth يستخدمه الدخول |
| `AUTH_PASSWORD` | كلمة قوية | كلمة دخول اللوحة | كلمة ضعيفة تعرض النظام للاختراق |
| `AUTH_ROLE` | `admin` | صلاحية المستخدم الافتراضي | لو ليست admin بعض الصفحات قد تمنعك |
| `DATABASE_URL` | `sqlite:///./waact.db` | مكان قاعدة البيانات | لو تغير بالخطأ هتفتح قاعدة جديدة فاضية |
| `OPENAI_API_KEY` | `sk-...` | مفتاح الذكاء الاصطناعي | AI/RAG قد يفشل أو يستخدم fallback أقل جودة |
| `OPENAI_MODEL` | `gpt-4o-mini` | موديل الردود | موديل غير متاح يسبب فشل في AI |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | موديل فهرسة المعرفة | Knowledge/RAG قد يفشل عند رفع ملفات |
| `CHROMA_PERSIST_DIR` | `../chroma_db` | مكان قاعدة المعرفة | لو تغير ستظهر المعرفة كأنها فاضية |
| `WHATSAPP_CONNECTOR_URL` | `http://localhost:3001` | عنوان Connector الذي يرسل منه Backend رسائل | الإرسال من Dashboard لن يعمل |
| `WHATSAPP_WEBHOOK_SECRET` | قيمة سرية | حماية webhook بين Connector وBackend | لو لا يطابق connector ستفشل الرسائل بـ 401 |
| `REPORT_HOUR` | `8` | وقت توليد التقارير | التقارير قد تتأخر أو تولد بوقت غير مناسب |
| `FOLLOWUP_HOUR` | `10` | وقت المتابعات | تنبيهات المتابعة قد لا تكون في وقت العمل |

إعداد مقترح للإنتاج:

```env
APP_MODE=isp
APP_URL=http://localhost:8000
SECRET_KEY=change-to-a-long-random-value
DEBUG=false
AUTH_ENABLED=true
AUTH_USERNAME=admin
AUTH_PASSWORD=change-to-a-strong-password
AUTH_ROLE=admin
DATABASE_URL=sqlite:///./waact.db
OPENAI_API_KEY=your-real-ai-key
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
CHROMA_PERSIST_DIR=../chroma_db
CHROMA_COLLECTION=knowledge_base
WHATSAPP_CONNECTOR_URL=http://localhost:3001
WHATSAPP_WEBHOOK_SECRET=change-this-secret-and-match-connector
REPORT_HOUR=8
FOLLOWUP_HOUR=10
```

## 7. إعداد `whatsapp-connector/.env`

الملف المهم للـ Connector هو:

```text
whatsapp-connector/.env
```

يجب أن يكون مطابقًا للـ Backend في السر:

```env
BACKEND_URL=http://localhost:8000
WEBHOOK_SECRET=change-this-secret-and-match-backend
PORT=3001
```

شرح المتغيرات:

| المتغير | بيعمل إيه؟ | لو غلط |
|---|---|---|
| `BACKEND_URL` | المكان الذي يرسل له Connector رسائل واتساب الواردة | الرسائل لن تصل للـ Backend، وقد يرد connector برسالة خطأ عامة |
| `WEBHOOK_SECRET` | نفس قيمة `WHATSAPP_WEBHOOK_SECRET` | Backend سيرفض الرسائل بـ 401 |
| `PORT` | بورت تشغيل connector | لو البورت مش نفس `WHATSAPP_CONNECTOR_URL` الإرسال من dashboard يفشل |

## 8. تشغيل السيستم رسميًا

شغل Backend أولًا:

```powershell
cd "C:\Users\moham\OneDrive\سطح المكتب\mmnn\waact\backend"
"C:\Users\moham\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
```

ماذا يحدث هنا؟

هذا يفتح API والDashboard على `http://localhost:8000`، وينشئ الجداول لو قاعدة البيانات غير موجودة، ويشغل Scheduler للتقارير وتذكيرات Radius إذا مفعلة.

لو Backend لم يعمل:

Dashboard لن تفتح، Connector لن يقدر يسلم الرسائل، AI وRadius وRouter لن يعملوا.

شغل WhatsApp Connector ثانيًا في Terminal آخر:

```powershell
cd "C:\Users\moham\OneDrive\سطح المكتب\mmnn\waact\whatsapp-connector"
npm start
```

ماذا يحدث هنا؟

يفتح WhatsApp Web في وضع headless، يظهر QR لأول مرة، ويحفظ الجلسة في `whatsapp-connector/session-data`.

لو Connector لم يعمل:

اللوحة والبيانات القديمة ستعمل، لكن لا توجد رسائل واتساب داخلة أو خارجة.

## 9. ربط واتساب بالـ QR

افتح:

```text
http://localhost:8000/settings
```

أو راقب QR في Terminal الخاص بـ Connector.

خطوات الربط:

1. افتح WhatsApp على الموبايل.
2. ادخل إلى Linked Devices.
3. اعمل Scan للـ QR.
4. انتظر أن تصبح حالة connector `connected=true`.

لو لم تعمل Scan:

السيستم سيظل مفتوحًا لكن لن يستقبل رسائل واتساب ولن يرسل ردود.

لو الجلسة فصلت لاحقًا:

احذف أو اترك `session-data` حسب الحالة، ثم شغل connector واعمل Scan جديد.

## 10. فحص التشغيل بعد الفتح

افحص Backend:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

المفروض ترى `status=healthy` و`version=1.3.0`.

افحص Connector:

```powershell
Invoke-RestMethod http://localhost:3001/api/status
```

المفروض ترى حالة الاتصال ورقم واتساب إذا متصل.

افتح الصفحات الأساسية:

```text
http://localhost:8000/
http://localhost:8000/whatsapp-chats
http://localhost:8000/support
http://localhost:8000/isp
```

اختبار عملي من واتساب:

| الرسالة | المتوقع |
|---|---|
| `مرحبا` | رد AI أو رد ترحيبي حسب المعرفة والإعدادات |
| `حالة الاشتراك` | لو Radius مفعّل يرد بالحالة، لو غير مفعّل يحول للدعم بدون إيقاف auto reply نهائيًا |
| `محتاج اغير باسورد الواى فاى` | يدخل Flow تغيير WiFi، يطلب باسورد أو تأكيد، أو ينشئ طلب يدوي في `/support` |

## 11. تشغيل Radius/DMA رسميًا

صفحة الإعداد:

```text
Advanced / Admin -> Radius
```

المطلوب من مزود Radius/DMA:

| المطلوب | مثال | لماذا مهم؟ |
|---|---|---|
| Base URL | `https://dma.example.com` | عنوان API الحقيقي |
| Auth Mode | bearer/header/query/basic | طريقة المصادقة |
| API Key أو Username/Password | حسب النظام | السماح للنظام يقرأ المشتركين |
| Search Path | `/api/subscribers/search?q={query}` | البحث برقم العميل أو username |
| Detail Path | `/api/subscribers/{external_id}` | جلب تفاصيل الاشتراك |
| Sessions Path | `/api/subscribers/{external_id}/sessions` | معرفة IP الحالي للعميل |
| Field Map | `phone`, `status`, `expires_at`, `ip_address` | تحويل أسماء حقول DMA لأسماء يفهمها WAACT |

لو Radius غير مفعّل:

CRM وواتساب وAI والحملات ستعمل، لكن حالة الاشتراك، التذكيرات، Segments الخاصة بالاشتراك، واكتشاف IP من sessions لن تعمل.

لو Field Map غلط:

قد تظهر الاشتراكات بحالة خطأ، أرقام العملاء لا ترتبط، أو تواريخ الانتهاء تكون فارغة.

لو Sessions Path غير موجود:

حالة الاشتراك قد تعمل، لكن اكتشاف IP الحالي للراوتر لن يعمل من Radius sessions.

## 12. تشغيل Router/WiFi رسميًا

صفحة الإعداد:

```text
Advanced / Admin -> Routers
```

يوجد طريقتان:

| الطريقة | متى تستخدمها؟ | النتيجة |
|---|---|---|
| Static Router | عند معرفة IP وبيانات راوتر عميل محدد | تنفيذ أو اختبار على راوتر محدد |
| Auto Discovery | عند الاعتماد على Radius sessions أو snapshot أو MikroTik PPP | النظام يكتشف IP الحالي بدل إدخاله يدويًا |

البروتوكولات المتاحة:

| Protocol | الاستخدام | ملاحظات |
|---|---|---|
| `manual` | إنشاء طلب دعم يدوي | آمن عندما لا نعرف API الراوتر |
| `http_json` | راوتر أو ACS له HTTP endpoint واضح | يحتاج path وpayload صحيحين |
| `tplink_web` | TP-Link CPE | يحتاج endpoint/session flow الخاص بالموديل |
| `huawei_web` | Huawei CPE | يحتاج endpoint/session flow الخاص بالموديل |
| `ssh` أو `mikrotik_ssh` | MikroTik أو جهاز يدعم SSH | يحتاج `paramiko` وأمر آمن محدد |
| `tr069` | ACS/TR-069 | يحتاج منصة ACS حقيقية |

لو Router Auto Discovery غير مفعّل:

طلب تغيير WiFi سيعمل فقط لو الراوتر مربوط Static بالعميل، وإلا سيتحول إلى طلب يدوي في `/support`.

لو بيانات الراوتر غلط:

النظام لن يغير الباسورد تلقائيًا، وسيسجل فشل أو يترك الطلب Manual Required.

لو تستخدم SSH ولم تثبت `paramiko`:

سيظهر خطأ `SSH execution requires installing paramiko.` والتغيير لن يتم.

تثبيت `paramiko` عند الحاجة فقط:

```powershell
cd "C:\Users\moham\OneDrive\سطح المكتب\mmnn\waact\backend"
"C:\Users\moham\AppData\Local\Programs\Python\Python312\python.exe" -m pip install paramiko
```

تحذير مهم:

AI لا ينفذ أوامر راوتر خام. تنفيذ الراوتر يتم من backend فقط، عبر إعدادات واضحة، مع سجل Audit/Action Logs، وبعد تأكيد العميل في Flow تغيير WiFi.

## 13. Knowledge Base وAI

صفحة المعرفة:

```text
Advanced / Admin -> قاعدة المعرفة
```

ارفع ملفات الأسعار، سياسة الاشتراك، مواعيد العمل، حلول المشاكل المتكررة. النظام يفهرسها في ChromaDB حتى يستخدمها AI في الردود.

لو لم ترفع Knowledge:

AI قد يرد بردود عامة، ولن يعرف أسعارك أو سياساتك الداخلية.

لو `OPENAI_API_KEY` بدون رصيد:

قد ترى خطأ مثل `insufficient_quota`. وقتها الردود الذكية أو embeddings قد تفشل، لكن باقي النظام مثل CRM وWhatsApp والطلبات يستمر.

## 14. الحملات والتسويق

صفحة الحملات:

```text
/campaigns
```

تستخدم لإرسال رسائل جماعية للعملاء. تدعم متغيرات مثل:

```text
{name}
{phone}
{status}
{service}
```

لو WhatsApp Connector غير متصل:

الحملة قد تتسجل لكن الإرسال الفعلي لن ينجح.

لو العميل أرسل `إلغاء`:

يدخل Opt-Out ولا يجب استهدافه في الحملات.

## 15. الدعم والطلبات اليومية

صفحة التشغيل اليومية للموظف:

```text
/support
```

تحتوي على:

| القسم | معناه | إجراء الموظف |
|---|---|---|
| طلبات الدعم | محادثات محتاجة تدخل بشري | استلام أو حل الطلب |
| طلبات WiFi | تغيير باسورد لم ينفذ تلقائيًا أو ينتظر تأكيد | تنفيذ يدويًا ثم الضغط `تم يدويًا` أو `إغلاق` |
| المتابعات | مهام Follow-up للعملاء | الضغط `تم` بعد التنفيذ |

لو الموظف لا يراجع `/support`:

طلبات العملاء الصعبة ستظل معلقة، حتى لو AI والردود العامة تعمل.

## 16. النسخ الاحتياطي

استخدم صفحة:

```text
Advanced / Admin -> Maintenance
```

أو انسخ الملفات المهمة يدويًا:

| الملف أو المجلد | لماذا مهم؟ |
|---|---|
| `backend/waact.db` | قاعدة العملاء والمحادثات والطلبات |
| `backend/radius_settings.json` | إعدادات Radius إذا تم حفظها |
| `backend/router_auto_settings.json` | إعدادات Auto Discovery |
| `chroma_db` أو قيمة `CHROMA_PERSIST_DIR` | قاعدة معرفة AI |
| `whatsapp-connector/session-data` | جلسة واتساب |
| `backend/.env` و`whatsapp-connector/.env` | إعدادات التشغيل والأسرار |

لو لم تعمل Backup:

أي تلف في الجهاز أو حذف بالخطأ قد يفقد العملاء والمحادثات والجلسة.

## 17. أوامر التحقق قبل التسليم الرسمي

نفذ فحص Python:

```powershell
cd "C:\Users\moham\OneDrive\سطح المكتب\mmnn\waact\backend"
"C:\Users\moham\AppData\Local\Programs\Python\Python312\python.exe" -m py_compile dashboard\routes.py config.py check_mvp_v1_3.py
```

نفذ فحص Node:

```powershell
cd "C:\Users\moham\OneDrive\سطح المكتب\mmnn\waact\whatsapp-connector"
node --check index.js
```

نفذ فحص MVP الكامل:

```powershell
cd "C:\Users\moham\OneDrive\سطح المكتب\mmnn\waact\backend"
"C:\Users\moham\AppData\Local\Programs\Python\Python312\python.exe" check_mvp_v1_3.py
```

لو فحص MVP فشل:

لا تسلم النظام رسميًا قبل معرفة الخطأ، لأنه يفحص Health، الصفحات الأساسية، Router flow، WiFi intent، وعدم إيقاف auto reply بسبب أخطاء Radius الناعمة.

## 18. تشغيل دائم بدل Terminal يدوي

للتجربة، Terminalين يكفوا. للتشغيل الرسمي، الأفضل تشغيل Backend وConnector كخدمات دائمة.

على Windows يمكنك استخدام Task Scheduler أو NSSM لتشغيل:

```text
Backend command: python -m uvicorn main:app --host 0.0.0.0 --port 8000
Backend working directory: backend
```

```text
Connector command: npm start
Connector working directory: whatsapp-connector
```

لو لم تستخدم خدمة دائمة:

عند إغلاق Terminal أو إعادة تشغيل الجهاز سيتوقف النظام.

## 19. قواعد أمان قبل الإنتاج

نفذ الآتي قبل تشغيله عند عميل حقيقي:

| الإجراء | لماذا؟ |
|---|---|
| `AUTH_ENABLED=true` | حماية لوحة التحكم |
| `DEBUG=false` | منع تسريب تفاصيل الأخطاء |
| تغيير `SECRET_KEY` | حماية جلسات المستخدمين |
| تغيير `WHATSAPP_WEBHOOK_SECRET` ومطابقته | منع رسائل مزيفة للـ webhook |
| عدم فتح بورت `3001` للعامة | Connector يحتوي API إرسال واتساب ويجب أن يبقى داخليًا |
| Backup يومي | حماية بيانات العملاء |
| رقم واتساب مخصص | تجنب مشاكل رقم شخصي أو فصل غير متوقع |

## 20. أشهر الأعطال ومعناها

| العطل | السبب المحتمل | الحل |
|---|---|---|
| Dashboard لا تفتح | Backend متوقف أو بورت 8000 مشغول | شغل Backend أو غير البورت |
| Connector disconnected | QR لم يتم مسحه أو جلسة WhatsApp فصلت | افتح `/settings` واعمل Scan QR |
| Webhook 401 | `WEBHOOK_SECRET` لا يطابق `WHATSAPP_WEBHOOK_SECRET` | وحد السر في الملفين |
| AI لا يرد | API key ناقص، quota انتهى، أو الإنترنت ضعيف | افحص `/ai-usage` والمفتاح والرصيد |
| Radius disabled | إعداد Radius غير مفعّل | فعله من صفحة Radius وأدخل endpoints |
| Router manual_required | لا يوجد API/credentials صالحة للراوتر | نفذ يدويًا من `/support` أو أكمل إعداد الراوتر |
| Port already in use | برنامج آخر يستخدم 8000 أو 3001 | أغلق البرنامج أو غير البورت |
| `capture() takes 1 positional argument...` | Warning معروف من بيئة/مكتبة | غير مانع طالما health والرسائل تعمل |

## 21. ما الذي يعمل بدون التكاملات الخارجية؟

بدون Radius:

CRM، Inbox، AI العام، الحملات، المتابعات، والتقارير تعمل. حالة الاشتراك والتذكيرات الدقيقة واكتشاف IP لن يعملوا.

بدون Router API:

Flow تغيير WiFi يستقبل الطلب ويحوّله للدعم. التغيير التلقائي لن يتم.

بدون OpenAI أو رصيد AI:

WhatsApp واستقبال الرسائل والـ CRM يعملوا. الرد الذكي وKnowledge/RAG يتأثروا.

بدون WhatsApp Connector:

Dashboard والبيانات تعمل. لا يوجد استقبال أو إرسال واتساب مباشر.

بدون Auth:

النظام يعمل تقنيًا، لكنه غير آمن للتشغيل عند عميل حقيقي.

## 22. Checklist التسليم الرسمي

قبل ما تقول إن السيستم جاهز رسميًا:

| البند | الحالة المطلوبة |
|---|---|
| Backend health | `/api/health` يرجع healthy |
| Connector status | `/api/status` على بورت 3001 يرجع connected |
| QR | ممسوح برقم الشركة |
| Auth | مفعّل بكلمة قوية |
| Debug | `false` |
| Secrets | مختلفة عن الافتراضي ومتطابقة بين backend وconnector |
| Backup | تم عمل نسخة من DB وsession-data و.env |
| AI | تم اختبار رد فعلي ورسالة معرفة |
| Radius | تم الاختبار أو موثق أنه غير متاح |
| Router | تم الاختبار أو موثق أنه Manual |
| Support page | تظهر الطلبات ويعرف الموظف يستخدمها |
| MVP check | `check_mvp_v1_3.py` ناجح |

## 23. الحالة الحالية بعد آخر تعديل

تم تنفيذ الآتي:

| التعديل | النتيجة |
|---|---|
| إضافة `/support` | صفحة واحدة لطلبات الدعم، WiFi، والمتابعات |
| إضافة `/isp` | صفحة بحث مبسطة عن الاشتراك والراوتر |
| تبسيط القائمة | 7 صفحات رئيسية فقط للعميل والموظف |
| نقل الفنيات إلى Advanced | النظام لم يفقد أي صفحة تقنية |
| إضافة `APP_MODE=isp` | الوضع الافتراضي مناسب لشركة ISP |
| تحديث فحص MVP | الفحص الآن يتأكد من الصفحات الجديدة |

آخر فحص تم بنجاح:

```text
python -m py_compile dashboard\routes.py config.py check_mvp_v1_3.py
node --check index.js
python check_mvp_v1_3.py
```

النتيجة: `MVP V1.3 checks passed`.

## 24. Online Demo: GitHub Codespaces + Supabase + Vercel

هذا السيناريو هدفه عرض السيستم Online قبل العميل بدون تشغيله على جهازك وبدون `localhost` أمام العميل.

المعمارية:

```text
Vercel Demo URL
        |
        v
Vercel Proxy Function
        |
        v
GitHub Codespaces public port 8000
        |
        v
FastAPI Backend + WhatsApp Connector private port 3001
        |
        v
Supabase Postgres
```

ماذا يعني هذا؟

| الخدمة | دورها | ماذا يحدث لو توقفت؟ |
|---|---|---|
| Supabase | قاعدة بيانات العملاء والمحادثات والطلبات | الداتا لن تُقرأ أو تُكتب |
| GitHub Codespaces | يشغل Backend وWhatsApp Connector وChroma | السيستم كله يتوقف إذا نام Codespace |
| Vercel | يعطيك رابط عرض ثابت ويعمل proxy للـ Codespace | رابط العرض لا يفتح، لكن Codespace نفسه قد يظل يعمل |
| WhatsApp session-data | يحفظ ربط QR داخل Codespaces | لو اتحذف تحتاج Scan QR جديد |

### الملفات التي تم تجهيزها للديمو

| الملف | وظيفته |
|---|---|
| `INSTALL_UPLOAD_TOOLS.bat` | يثبت أو يفتح أدوات Git/Node/GitHub CLI المطلوبة للرفع |
| `CHECK_BEFORE_UPLOAD.bat` | يفحص الكود والأمان قبل رفع المشروع |
| `UPLOAD_TO_GITHUB.bat` | يجهز Git ويعمل commit وpush للريبو بأمان |
| `ONLINE_DEMO_UPLOAD_GUIDE.md` | خطوات مختصرة للرفع والتشغيل Online |
| `.devcontainer/devcontainer.json` | يجهز بيئة Codespaces بـ Python 3.12 وNode 20 |
| `scripts/codespaces_setup.sh` | يثبت مكتبات Python وNode ومكتبات Chromium |
| `scripts/start_online_demo.sh` | يشغل Backend وConnector معًا |
| `backend/.env.codespaces.example` | قالب إعدادات Backend للـ Online Demo |
| `whatsapp-connector/.env.codespaces.example` | قالب إعدادات Connector للـ Online Demo |
| `vercel.json` | يجعل Vercel يوجه كل الطلبات إلى proxy function |
| `api/proxy.js` | يقرأ `CODESPACE_BACKEND_URL` ويحول الطلبات إلى Codespaces |

### Step 1: إنشاء Supabase Database

1. افتح Supabase.
2. أنشئ Project جديد.
3. ادخل إلى Project Settings ثم Database.
4. انسخ Connection String من Transaction Pooler أو Session Pooler.
5. استخدم صيغة SQLAlchemy التالية:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:6543/postgres?sslmode=require
```

مهم:

لو كلمة المرور فيها رموز مثل `@` أو `#` أو `/` لازم تعمل لها URL encoding من Supabase أو من أداة آمنة، وإلا الاتصال هيفشل.

لو لم تضبط Supabase:

السيستم قد يرجع لـ SQLite داخل Codespaces، وهذا غير مناسب للديمو لأنه أقل ثباتًا وقد لا يوضح أن الداتا Cloud.

### Step 2: فتح المشروع على GitHub Codespaces

1. ارفع المشروع على GitHub repository خاص.
2. افتح repository.
3. اختر `Code` ثم `Codespaces` ثم `Create codespace`.
4. انتظر postCreateCommand حتى ينتهي.

ما الذي سيحدث تلقائيًا؟

`scripts/codespaces_setup.sh` سيعمل الآتي:

| العملية | السبب |
|---|---|
| تثبيت Chromium runtime libraries | لأن `whatsapp-web.js` يحتاج Chrome/Puppeteer |
| `pip install -r backend/requirements.txt` | تشغيل FastAPI وSQLAlchemy وSupabase driver |
| `npm install --prefix whatsapp-connector` | تشغيل WhatsApp Connector |
| إنشاء `backend/.env` من example إذا غير موجود | بداية إعداد آمنة بدون أسرار حقيقية |
| إنشاء `whatsapp-connector/.env` من example إذا غير موجود | بداية إعداد آمنة للConnector |

لو setup فشل بسبب package ناقص:

أعد تشغيل:

```bash
bash scripts/codespaces_setup.sh
```

### Step 3: ضبط أسرار Backend في Codespaces

افتح `backend/.env` داخل Codespaces وعدل القيم:

```env
APP_MODE=isp
APP_URL=https://YOUR-VERCEL-DEMO.vercel.app
SECRET_KEY=long-random-secret
DEBUG=false
AUTH_ENABLED=true
AUTH_USERNAME=admin
AUTH_PASSWORD=strong-password
AUTH_ROLE=admin

DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:6543/postgres?sslmode=require

OPENAI_API_KEY=your-ai-key
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

CHROMA_PERSIST_DIR=./chroma_db
CHROMA_COLLECTION=knowledge_base

WHATSAPP_CONNECTOR_URL=http://127.0.0.1:3001
WHATSAPP_WEBHOOK_SECRET=same-webhook-secret
WHATSAPP_CONNECTOR_API_KEY=same-connector-internal-key
```

شرح الأهم:

| المتغير | لماذا مهم؟ |
|---|---|
| `APP_URL` | اجعله Vercel URL حتى يظهر الرابط الرسمي في النظام |
| `DATABASE_URL` | يربط الداتا بـ Supabase بدل SQLite |
| `WHATSAPP_CONNECTOR_URL` | يبقى داخليًا داخل Codespaces، لا تضع Vercel هنا |
| `WHATSAPP_WEBHOOK_SECRET` | يحمي الرسائل القادمة من Connector إلى Backend |
| `WHATSAPP_CONNECTOR_API_KEY` | يحمي APIs الخاصة بالConnector مثل send/chats/media/logout |

لو `DEBUG=true` في الديمو:

قد تظهر تفاصيل أخطاء للعميل. اجعلها `false`.

### Step 4: ضبط أسرار Connector في Codespaces

افتح `whatsapp-connector/.env` وعدل:

```env
BACKEND_URL=http://127.0.0.1:8000
WEBHOOK_SECRET=same-webhook-secret
CONNECTOR_API_KEY=same-connector-internal-key
HOST=127.0.0.1
PORT=3001
LOGOUT_ON_SHUTDOWN=false
```

مهم:

| المتغير | المطلوب |
|---|---|
| `WEBHOOK_SECRET` | يطابق `WHATSAPP_WEBHOOK_SECRET` في Backend |
| `CONNECTOR_API_KEY` | يطابق `WHATSAPP_CONNECTOR_API_KEY` في Backend |
| `HOST=127.0.0.1` | يمنع فتح connector مباشرة للعامة |
| `LOGOUT_ON_SHUTDOWN=false` | يحافظ على WhatsApp session عند restart |

لو `HOST=0.0.0.0` وport 3001 public:

هذا خطر، لأن أي شخص قد يحاول استخدام API إرسال واتساب إذا عرف الرابط والمفتاح ضعيف.

### Step 5: تشغيل الديمو داخل Codespaces

نفذ:

```bash
bash scripts/start_online_demo.sh
```

هذا يشغل:

| العملية | البورت | الظهور |
|---|---|---|
| Backend | `8000` | Public Codespaces URL |
| WhatsApp Connector | `3001` | Private داخل Codespaces |

افتح تبويب Ports في Codespaces واجعل بورت `8000` Public إذا لم يكن كذلك.

اختبر Backend URL المباشر:

```text
https://YOUR-CODESPACE-8000.app.github.dev/api/health
```

### Step 6: ربط Vercel بالـ Codespace

في Vercel:

1. اربط نفس GitHub repository.
2. Deploy المشروع من root folder.
3. افتح Project Settings ثم Environment Variables.
4. أضف:

```env
CODESPACE_BACKEND_URL=https://YOUR-CODESPACE-8000.app.github.dev
```

5. اعمل Redeploy.

الآن افتح:

```text
https://YOUR-VERCEL-DEMO.vercel.app
```

لو ظهرت صفحة Setup بدل Dashboard:

معناه أن `CODESPACE_BACKEND_URL` غير مضبوط في Vercel أو لم تعمل Redeploy بعد إضافته.

لو Vercel يعطي 502:

غالبًا Codespace متوقف أو port 8000 ليس Public أو الرابط تغير.

### Step 7: ربط WhatsApp QR

افتح من Vercel:

```text
/settings
```

أو افتح Codespaces logs وشوف QR.

اعمل Scan من رقم واتساب تجريبي مخصص للديمو.

لا تستخدم رقم العميل في أول تجربة.

لو QR لا يظهر:

راجع Terminal الخاص بـ `scripts/start_online_demo.sh`، وتأكد أن connector لم يفشل بسبب Chromium dependencies أو session قديمة تالفة.

### Step 8: اختبار قبل عرض العميل

اختبر الآتي بالترتيب:

| الاختبار | الرابط/الرسالة | المتوقع |
|---|---|---|
| Health | `/api/health` | healthy وversion 1.3.0 |
| Login | `/login` | يدخل بكلمة المرور |
| Dashboard | `/` | يفتح القائمة المبسطة |
| WhatsApp status | `/settings` | connected بعد QR |
| Inbox | `/whatsapp-chats` | يظهر chats |
| رسالة عادية | `مرحبا` | رد AI أو رد fallback |
| WiFi flow | `محتاج اغير باسورد الواى فاى` | يبدأ flow أو يظهر في `/support` |
| Support | `/support` | طلبات الدعم وWiFi تظهر |
| ISP | `/isp` | صفحة بحث الاشتراك والراوتر تفتح |
| Campaign small | رقمك فقط | يتسجل ويرسل لو connector متصل |

داخل Codespaces شغل فحص MVP:

```bash
cd backend
python check_mvp_v1_3.py
```

لو الفحص فشل بسبب Supabase:

راجع `DATABASE_URL` وSSL وPassword encoding.

### Step 9: ملاحظات مهمة للعرض

هذه النسخة تصلح كـ Online Demo قبل العميل، لكنها ليست تسليم نهائي طويل المدى.

| السبب | التفاصيل |
|---|---|
| Codespaces ينام | إذا توقف، WhatsApp والBackend يتوقفوا |
| URL قد يتغير | إذا Codespace جديد، حدث `CODESPACE_BACKEND_URL` في Vercel |
| WhatsApp Web غير رسمي | مناسب للديمو، لكن التسليم الجاد يحتاج VPS أو WhatsApp Cloud API حسب الاتفاق |
| Radius/Router يحتاج وصول شبكة | لو API العميل داخلي، الديمو سيعرضه Manual أو Mock فقط |

### Checklist الديمو قبل مكالمة العميل

| البند | الحالة المطلوبة |
|---|---|
| Codespace running | Terminal مفتوح و`start_online_demo.sh` يعمل |
| Port 8000 | Public |
| Vercel env | `CODESPACE_BACKEND_URL` مضبوط |
| Supabase | `DATABASE_URL` صحيح والداتا تتسجل |
| Auth | مفعل وكلمة المرور معروفة لك فقط |
| WhatsApp | connected برقم تجريبي |
| AI | مفتاح شغال أو fallback واضح |
| Support | صفحة `/support` تفتح |
| MVP check | ناجح داخل Codespaces |
