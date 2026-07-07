# WAACT Online Demo Upload Guide

الدليل ده يمشيك خطوة بخطوة عشان ترفع المشروع على GitHub وتشغله Online Demo باستخدام GitHub Codespaces + Supabase + Vercel.

## 1. الملفات الجاهزة

| الملف | تستخدمه إمتى؟ |
|---|---|
| `INSTALL_UPLOAD_TOOLS.bat` | أول مرة فقط لو Git أو Node مش متثبتين |
| `CHECK_BEFORE_UPLOAD.bat` | قبل الرفع، يفحص Python وNode وVercel proxy وMVP smoke test |
| `UPLOAD_TO_GITHUB.bat` | يجهز Git ويعمل commit وpush للريبو |
| `.devcontainer/devcontainer.json` | GitHub Codespaces يستخدمه تلقائيًا |
| `scripts/start_online_demo.sh` | يشغل Backend وWhatsApp Connector داخل Codespaces |
| `vercel.json` و`api/proxy.js` | يخلي Vercel يفتح Dashboard من Codespaces |

## 2. اعمل GitHub repo فاضي

قبل GitHub repo، تأكد أن Git موجود على الجهاز. شغل:

```text
INSTALL_UPLOAD_TOOLS.bat
```

لو السكربت ثبت Git أو Node، اقفل نافذة Terminal وافتح واحدة جديدة بعد التثبيت.

1. افتح GitHub.
2. اضغط New repository.
3. الاسم المقترح: `waact-online-demo`.
4. خليه Private لو الديمو للعميل.
5. لا تضيف README ولا `.gitignore` من GitHub.
6. انسخ رابط الريبو، مثال:

```text
https://github.com/YOUR_USERNAME/waact-online-demo.git
```

## 3. ارفع المشروع بضغطة واحدة

من مجلد المشروع افتح:

```text
UPLOAD_TO_GITHUB.bat
```

السكربت سيعمل الآتي:

| الخطوة | ماذا تفعل؟ |
|---|---|
| Safety checks | يتأكد أن الكود سليم |
| Git init | ينشئ repo محلي لو غير موجود |
| Remove secrets from tracking | يمنع رفع `.env` وsession وDB |
| Remote origin | يطلب منك GitHub repo URL |
| Commit | يعمل commit للملفات |
| Push | يرفع على GitHub branch `main` |

لو ظهر push failed بسبب Login:

استخدم GitHub Desktop أو نفذ:

```powershell
gh auth login
```

ثم شغل `UPLOAD_TO_GITHUB.bat` مرة ثانية.

## 4. جهز Supabase

1. افتح Supabase.
2. أنشئ Project.
3. ادخل Project Settings ثم Database.
4. انسخ Connection String من Pooler.
5. الصيغة المطلوبة داخل Codespaces:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:6543/postgres?sslmode=require
```

لو كلمة السر فيها رموز، استخدم النسخة الجاهزة من Supabase أو اعمل URL encoding.

## 5. افتح GitHub Codespaces

1. افتح repo على GitHub.
2. اضغط Code.
3. افتح Codespaces.
4. اضغط Create codespace on main.
5. انتظر setup يخلص.

بعد الفتح، لو لم يشتغل setup تلقائيًا نفذ:

```bash
bash scripts/codespaces_setup.sh
```

## 6. عدل ملفات البيئة داخل Codespaces

افتح `backend/.env` وعدل:

```env
APP_URL=https://YOUR-VERCEL-DEMO.vercel.app
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:6543/postgres?sslmode=require
OPENAI_API_KEY=your-key
WHATSAPP_WEBHOOK_SECRET=make-one-secret
WHATSAPP_CONNECTOR_API_KEY=make-another-secret
AUTH_PASSWORD=strong-password
DEBUG=false
AUTH_ENABLED=true
```

افتح `whatsapp-connector/.env` وعدل نفس الأسرار:

```env
BACKEND_URL=http://127.0.0.1:8000
WEBHOOK_SECRET=same-as-WHATSAPP_WEBHOOK_SECRET
CONNECTOR_API_KEY=same-as-WHATSAPP_CONNECTOR_API_KEY
HOST=127.0.0.1
PORT=3001
LOGOUT_ON_SHUTDOWN=false
```

## 7. شغل الديمو في Codespaces

نفذ:

```bash
bash scripts/start_online_demo.sh
```

افتح تبويب Ports في Codespaces:

| Port | المطلوب |
|---|---|
| 8000 | Public |
| 3001 | Private |

انسخ رابط بورت 8000، مثال:

```text
https://YOUR-CODESPACE-8000.app.github.dev
```

اختبر:

```text
https://YOUR-CODESPACE-8000.app.github.dev/api/health
```

## 8. اربط Vercel

1. افتح Vercel.
2. Import Project من GitHub repo.
3. Root Directory يظل root المشروع.
4. بعد أول deploy، افتح Settings ثم Environment Variables.
5. أضف:

```env
CODESPACE_BACKEND_URL=https://YOUR-CODESPACE-8000.app.github.dev
```

6. اعمل Redeploy.
7. افتح Vercel URL.

لو ظهرت صفحة Setup:

راجع `CODESPACE_BACKEND_URL` واعمل Redeploy.

لو ظهر 502:

راجع أن Codespace شغال وأن Port 8000 Public.

## 9. اختبار قبل العميل

اختبر بالترتيب:

| الاختبار | المطلوب |
|---|---|
| `/api/health` | healthy |
| `/login` | دخول بكلمة المرور |
| `/settings` | WhatsApp QR أو connected |
| Scan QR | من رقم تجريبي |
| `/whatsapp-chats` | تظهر المحادثات |
| رسالة `مرحبا` | النظام يرد |
| رسالة `محتاج اغير باسورد الواى فاى` | يظهر Flow أو طلب في `/support` |
| `/support` | الطلبات تظهر |
| `/isp` | صفحة ISP تفتح |

## 10. مهم جدًا

هذه نسخة Demo Online. ليست تسليم Production نهائي لأن Codespaces ممكن ينام. لو العميل وافق، التسليم الحقيقي الأفضل يكون VPS أو سيرفر عند العميل، خصوصًا لو Radius/Router داخل شبكة خاصة.
