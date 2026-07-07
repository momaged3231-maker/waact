const { Client, LocalAuth } = require('whatsapp-web.js');
const express = require('express');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
require('dotenv').config();

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const PORT = process.env.PORT || 3001;
const HOST = process.env.HOST || '127.0.0.1';
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || 'waact-secret';
const CONNECTOR_API_KEY = process.env.CONNECTOR_API_KEY || '';
const LOGOUT_ON_SHUTDOWN = String(process.env.LOGOUT_ON_SHUTDOWN || 'false').toLowerCase() === 'true';

const app = express();
app.use(express.json());

function requireConnectorKey(req, res, next) {
    if (!CONNECTOR_API_KEY) {
        return next();
    }
    if (req.get('X-Connector-Key') !== CONNECTOR_API_KEY) {
        return res.status(401).json({ error: 'Unauthorized connector request' });
    }
    next();
}

app.use('/api', requireConnectorKey);

let clientReady = false;
let lastQR = null;
const messageCache = new Map();
const MESSAGE_CACHE_LIMIT = 2000;

const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: './session-data'
    }),
    puppeteer: {
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--window-size=800,600',
            '--disable-blink-features=AutomationControlled',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
        ]
    }
});

client.on('qr', (qr) => {
    lastQR = qr;
    qrcode.generate(qr, { small: true });
    console.log('\n[QR CODE] Scan the QR above with WhatsApp to connect.\n');
});

client.on('ready', () => {
    clientReady = true;
    console.log('[WHATSAPP] Client is ready!');
    console.log(`[WHATSAPP] Connected as: ${client.info.wid.user}`);
});

client.on('message', async (msg) => {
    if (msg.from.includes('status@broadcast') || msg.from.includes('group')) {
        return;
    }

    const phone = await resolvePhoneFromMessage(msg);
    const messageId = cacheMessage(msg) || msg.id.id;

    let messageText = msg.body;
    const hasMedia = msg.hasMedia;
    const mediaType = hasMedia ? (msg.type || 'media') : null;

    if (hasMedia) {
        if (msg._data && msg._data.caption) {
            messageText = msg._data.caption;
        } else {
            messageText = `[${mediaType || 'ملف وسائط'}]`;
        }
    }

    if (!messageText) {
        console.log(`[SKIPPED] From: ${phone} | Empty message (${mediaType || 'unknown'})`);
        return;
    }

    console.log(`[INCOMING] From: ${phone} | Type: ${mediaType || 'text'} | Msg: ${messageText.substring(0, 100)}`);

    try {
        const response = await axios.post(`${BACKEND_URL}/api/whatsapp/webhook`, {
            phone: phone,
            message: messageText,
            message_id: messageId,
            timestamp: msg.timestamp,
            media_type: mediaType,
        }, {
            headers: {
                'Content-Type': 'application/json',
                'X-Webhook-Secret': WEBHOOK_SECRET,
            },
            timeout: 30000,
        });

        const replyText = response.data.reply;
        if (replyText) {
            await msg.reply(replyText);
            console.log(`[REPLIED] To: ${phone} | ${replyText.substring(0, 100)}`);
        }
    } catch (error) {
        console.error(`[ERROR] Processing message from ${phone}:`, error.message);
        try {
            await msg.reply('عذراً، حدث خطأ في النظام. سيتم الرد عليك في أقرب وقت.');
        } catch (e) {
            console.error('[ERROR] Failed to send error reply:', e.message);
        }
    }
});

async function resolvePhoneFromMessage(msg) {
    const raw = msg.from || '';
    try {
        const contact = await msg.getContact();
        if (contact && contact.number) {
            return String(contact.number).replace(/\D/g, '');
        }
        if (contact && contact.id && contact.id.user && !(contact.id._serialized || '').includes('@lid')) {
            return String(contact.id.user).replace(/\D/g, '');
        }
    } catch (error) {
        console.warn(`[WARN] Could not resolve contact for ${raw}: ${error.message}`);
    }
    return raw.replace(/@(c\.us|lid)$/i, '').replace(/\D/g, '') || raw.replace('@c.us', '').replace('@lid', '');
}

client.on('disconnected', (reason) => {
    clientReady = false;
    console.log(`[WHATSAPP] Disconnected: ${reason}`);
    console.log('[WHATSAPP] Attempting to reconnect...');
    client.initialize();
});

app.get('/api/status', (req, res) => {
    res.json({
        connected: clientReady,
        qr: lastQR,
        info: client.info ? {
            wid: client.info.wid.user,
            pushname: client.info.pushname,
        } : null,
    });
});

function mediaLabel(type) {
    const labels = {
        image: 'صورة',
        video: 'فيديو',
        audio: 'رسالة صوتية',
        ptt: 'رسالة صوتية',
        document: 'ملف',
        sticker: 'ملصق',
    };
    return labels[type] || 'وسائط';
}

function messagePreview(msg) {
    if (!msg) return '';
    const body = msg.body || '';
    if (msg.hasMedia && (!body || /^\[[^\]]+\]$/.test(body))) {
        return mediaLabel(msg.type);
    }
    return body;
}

function cacheMessage(msg) {
    const id = msg.id ? (msg.id._serialized || msg.id.id) : null;
    if (!id) return null;
    messageCache.set(id, msg);
    if (messageCache.size > MESSAGE_CACHE_LIMIT) {
        const firstKey = messageCache.keys().next().value;
        messageCache.delete(firstKey);
    }
    return id;
}

function serializeMessage(msg) {
    const id = cacheMessage(msg);
    const raw = msg._data || {};
    const item = {
        id,
        body: msg.body || '',
        fromMe: msg.fromMe,
        timestamp: msg.timestamp,
        type: msg.type,
        hasMedia: msg.hasMedia,
        media: msg.hasMedia ? {
            mimetype: raw.mimetype || null,
            filename: raw.filename || `${msg.type || 'media'}`,
        } : null,
    };
    return item;
}

app.get('/api/messages/:messageId/media', async (req, res) => {
    if (!clientReady) {
        return res.status(503).json({ error: 'WhatsApp client not connected' });
    }

    const msg = messageCache.get(req.params.messageId);
    if (!msg || !msg.hasMedia) {
        return res.status(404).json({ error: 'Media not found. Open the chat messages first.' });
    }

    try {
        const media = await msg.downloadMedia();
        if (!media || !media.data) {
            return res.status(404).json({ error: 'Media is not available from WhatsApp' });
        }

        const buffer = Buffer.from(media.data, 'base64');
        res.setHeader('Content-Type', media.mimetype || 'application/octet-stream');
        res.setHeader('Cache-Control', 'private, max-age=3600');
        if (media.filename) {
            res.setHeader('Content-Disposition', `inline; filename="${media.filename.replace(/"/g, '')}"`);
        }
        res.send(buffer);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/chats', async (req, res) => {
    if (!clientReady) {
        return res.status(503).json({ error: 'WhatsApp client not connected' });
    }
    try {
        const chats = await client.getChats();
        const list = chats
            .filter(c => !c.id._serialized.includes('status'))
            .sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
            .slice(0, 50)
            .map(c => ({
                id: c.id._serialized,
                name: c.name || c.id.user,
                phone: c.id.user,
                isGroup: c.isGroup,
                unreadCount: c.unreadCount,
                timestamp: c.timestamp,
                lastMessage: c.lastMessage ? {
                    body: c.lastMessage.body,
                    preview: messagePreview(c.lastMessage),
                    fromMe: c.lastMessage.fromMe,
                    timestamp: c.lastMessage.timestamp,
                    type: c.lastMessage.type,
                    hasMedia: c.lastMessage.hasMedia,
                } : null,
            }));
        res.json({ chats: list });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/chats/:chatId/messages', async (req, res) => {
    if (!clientReady) {
        return res.status(503).json({ error: 'WhatsApp client not connected' });
    }
    try {
        const chat = await client.getChatById(req.params.chatId);
        const limit = Math.min(parseInt(req.query.limit) || 50, 80);
        const msgs = await chat.fetchMessages({ limit });
        msgs.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
        const list = msgs.map(serializeMessage);
        res.json({ messages: list, chatName: chat.name });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/qr', (req, res) => {
    if (lastQR) {
        res.json({ qr: lastQR });
    } else {
        res.json({ qr: null, message: 'No QR available. Client might be connected.' });
    }
});

app.post('/api/send', async (req, res) => {
    const { phone, chatId, message } = req.body;
    if ((!phone && !chatId) || !message) {
        return res.status(400).json({ error: 'Phone/chatId and message are required' });
    }

    if (!clientReady) {
        return res.status(503).json({ error: 'WhatsApp client not connected' });
    }

    try {
        const target = chatId || `${phone}@c.us`;
        const sent = await client.sendMessage(target, message);
        res.json({
            success: true,
            message: 'Message sent',
            message_id: sent && sent.id ? (sent.id._serialized || sent.id.id) : null,
            chat_id: target,
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/logout', async (req, res) => {
    try {
        await client.logout();
        clientReady = false;
        res.json({ success: true, message: 'Logged out' });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.listen(PORT, HOST, () => {
    console.log(`[SERVER] WhatsApp Connector running on ${HOST}:${PORT}`);
    console.log(`[SERVER] Backend URL: ${BACKEND_URL}`);
});

client.initialize();

process.on('SIGINT', async () => {
    console.log('\n[SHUTDOWN] Cleaning up...');
    if (LOGOUT_ON_SHUTDOWN) {
        try {
            await client.logout();
        } catch (e) {
            // ignore
        }
    }
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.log('\n[SHUTDOWN] Received SIGTERM.');
    if (LOGOUT_ON_SHUTDOWN) {
        try {
            await client.logout();
        } catch (e) {
            // ignore
        }
    }
    process.exit(0);
});
