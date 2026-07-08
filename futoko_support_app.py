"""
不登校 対応サポート（道教委版）
先生の相談に、国・北海道の方針にそって、対応のヒントを端的に表示します。

土台にした資料:
  ・教育機会確保法（H28）と基本指針、令和元年通知「支援の在り方について」（文科省）
  ・生徒指導提要（改訂版・R4.12／文科省）
  ・COCOLOプラン（R5.3／文科省）
  ・HOKKAIDO不登校対策プラン（道教委）
  ・不登校支援ガイドブック「全ての子どもの笑顔のために」（R5.12／道教委）

実行: streamlit run futoko_support_app.py
APIキー: .streamlit/secrets.toml の ANTHROPIC_API_KEY / 環境変数 / サイドバー入力
"""

import os
import re
import json
import streamlit as st
from anthropic import Anthropic

MODEL = "claude-haiku-4-5"

GRADES = ["小学校", "中学校", "高校", "その他"]
ABSENCE = ["行き渋り", "断続的に欠席", "連続して欠席", "教室に入れない", "別室には来られる"]
BACKGROUNDS = ["学習・進路", "友人関係", "いじめの疑い", "家庭の状況",
               "心身の不調", "生活リズム", "発達特性", "きっかけ不明"]

# 一次資料リンク（実在URL・確認済み）
LINKS_KUNI = [
    ("教育機会確保法・基本指針", "https://www.mext.go.jp/a_menu/shotou/seitoshidou/1384370.htm"),
    ("支援の在り方について（R元通知）", "https://www.mext.go.jp/a_menu/shotou/seitoshidou/1422155.htm"),
    ("生徒指導提要（改訂版）", "https://www.mext.go.jp/a_menu/shotou/seitoshidou/1404008_00001.htm"),
    ("COCOLOプラン", "https://www.mext.go.jp/a_menu/shotou/seitoshidou/1397802_00005.htm"),
]
LINKS_DO = [
    ("HOKKAIDO不登校対策プラン", "https://www.dokyoi.pref.hokkaido.lg.jp/hk/ssa/hokkaido-futoukoutaisaku-plan.html"),
    ("不登校支援ガイドブック", "https://www.dokyoi.pref.hokkaido.lg.jp/hk/ssa/hutoukou-guidebook.html"),
    ("道教委 不登校支援ポータル", "https://www.dokyoi.pref.hokkaido.lg.jp/hk/ssa/hutoukouportal.html"),
]

SYSTEM_PROMPT = """あなたは、国と北海道教育委員会の不登校対策に精通した教育相談の専門家です。北海道の先生の相談に、方針に沿って端的に、あたたかく助言します。

【土台となる方針】
■教育機会確保法(H28)・基本指針・支援の在り方通知(R元.10.25)：不登校はどの子にも起こり得る。不登校というだけで問題行動と見ない。児童生徒の最善の利益を最優先し、意思を尊重、本人・保護者を追い詰めない。登校を結果目標にせず社会的自立を目指す。休養の必要性を踏まえ、多様で適切な学びの場・ICT活用・出席扱いを確保。情報は関係者で組織的・継続的に共有。
■生徒指導提要(改訂版/R4.12)：自発的・主体的な発達を支え、社会的資質・能力と自己実現、自己指導能力の育成を目指す。日常の発達支持的生徒指導（挨拶・声かけ・励まし・対話）を土台に、先手を打つ常態的・先行的な関わりを重視。担任が抱え込まずチームで、アセスメントに基づき役割分担。こども基本法（意見表明・最善の利益）を尊重。
■COCOLOプラン(R5.3)：「①多様な学びの場を確保（学びの多様化学校・校内教育支援センター＝スペシャルサポートルーム・教育支援センター・ICT・出席扱い）②小さなSOSをチーム学校で早期に③学校風土の見える化で安心できる場に」。
■道教委(HOKKAIDO不登校対策プラン/ガイドブック)：目標は社会的自立（自己肯定感の回復、SOSを出せる力を支える）。アセスメントはBPSモデル（生物=睡眠・体調・発達特性／心理=学習・情緒・自己肯定感／社会=友人・いじめ・教職員・家庭・虐待の痕跡）。チーム学校（養護教諭・SC・SSW・生徒指導主事・教育相談コーディネーター）、児童生徒理解・支援シート、別室・校内教育支援センター、家庭訪問（了承を得て短時間・傾聴、登校を強く促さない）、保護者支援。

【緊急性】虐待・いじめ被害・自傷・希死念慮の兆候があれば最優先で管理職・関係機関へ。

【回答スタイル】多忙な現場の先生に寄り添う、あたたかく具体的なトーン。端的に。各項目は短い体言止め・一文。ダラダラ書かない。断定せず選択肢として。声かけは「」で短い例文。特に「次にとりたい行動」と「気を付けたいこと」は、その場ですぐ動ける具体性で。

【出力形式】JSONオブジェクトのみ返す（前置き・コードフェンス禁止）。日本語。
{
  "urgency": "none|elevated|high",
  "urgency_note": "elevated/highのみ、理由と最優先対応を一文。noneは空文字",
  "assessment": "BPSの視点で着目点を一文（短く。断定しない）",
  "basic_approach": "対応の基本方針を一文（短く）",
  "concrete_actions": ["具体的な声かけ・対応。短く。「」で例文含む。3個"],
  "collaboration": ["つなぐ先＋用件。短く。2〜3個"],
  "next_steps": ["次にとりたい行動。今日〜数日で動ける具体行動（心と身体のチェック/支援シート/別室・校内教育支援センター等を状況に応じ）。短く。3個"],
  "avoid": ["気を付けたいこと（避けたい対応）。短く体言止め。2〜3個"]
}"""


class ClaudeParseError(Exception):
    def __init__(self, raw, stop_reason):
        super().__init__("parse error")
        self.raw = raw
        self.stop_reason = stop_reason


def get_api_key():
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _extract_json(text):
    t = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "").strip()
    s, e = t.find("{"), t.rfind("}")
    if s >= 0 and e > s:
        t = t[s:e + 1]
    return re.sub(r",\s*([}\]])", r"\1", t)


def ask_claude(api_key, user_message):
    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL, max_tokens=2000, system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text").strip()
    try:
        return json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        raise ClaudeParseError(raw, getattr(resp, "stop_reason", "") or "")


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ───── 画面 ─────
st.set_page_config(page_title="不登校 対応サポート", page_icon="🌱", layout="centered")

st.markdown("""
<style>
.block-container{padding-top:1.1rem;max-width:720px;}
html,body,[class*="css"]{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP",system-ui,sans-serif;}
.stButton > button{background:#0f766e;color:#fff;border:none;border-radius:12px;
  padding:13px 0;font-weight:700;font-size:16px;width:100%;box-shadow:0 2px 6px rgba(15,118,110,.25);}
.stButton > button:hover{background:#0d685f;color:#fff;}
.hero{background:linear-gradient(135deg,#0e7490 0%,#0f766e 55%,#15803d 100%);
  border-radius:20px;padding:24px 24px 22px;color:#fff;margin-bottom:16px;
  box-shadow:0 6px 20px rgba(13,110,95,.28);}
.hero .badge{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.04em;
  background:rgba(255,255,255,.18);padding:4px 11px;border-radius:999px;margin-bottom:12px;}
.hero .headline{font-size:24px;font-weight:800;line-height:1.45;margin-bottom:10px;}
.hero .lead{font-size:13.5px;line-height:1.8;opacity:.95;}
.card{border-radius:14px;padding:14px 16px;margin-bottom:12px;
  box-shadow:0 1px 3px rgba(0,0,0,.06);}
.card .hd{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
.card .ic{font-size:18px;}
.card .tl{font-weight:800;font-size:15px;}
.card ul,.card ol{margin:0;padding-left:20px;}
.card li{margin:6px 0;line-height:1.65;font-size:14.5px;color:#1f2937;}
.card .tx{font-size:14.5px;line-height:1.75;color:#1f2937;}
.card ol li{padding-left:3px;}
.card ol li::marker{font-weight:800;color:#15803d;}
.xlist{list-style:none;padding-left:2px !important;}
.xlist li{position:relative;padding-left:22px;}
.xlist li::before{content:"✕";position:absolute;left:0;color:#d97706;font-weight:800;}
.ban{border-radius:14px;padding:14px 16px;margin-bottom:13px;font-size:14.5px;line-height:1.65;}
label{font-weight:600 !important;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="badge">🌱 先生のための 不登校 対応サポート</div>
  <div class="headline">気になるあの子のこと、<br>一緒に考えます。</div>
  <div class="lead">うまくいかない日も、先生ひとりで抱えなくて大丈夫です。
  状況を選んで相談すると、国と北海道の方針にそって、いま何ができるかを一緒に整理します。</div>
</div>
""", unsafe_allow_html=True)

with st.expander("📚 根拠となる資料を開く（国・北海道）"):
    st.markdown("**国（文部科学省）**")
    c1 = st.columns(2)
    for i, (name, url) in enumerate(LINKS_KUNI):
        c1[i % 2].link_button(name, url, use_container_width=True)
    st.markdown("**北海道（道教委）**")
    c2 = st.columns(2)
    for i, (name, url) in enumerate(LINKS_DO):
        c2[i % 2].link_button(name, url, use_container_width=True)

api_key = get_api_key()
if not api_key:
    api_key = st.sidebar.text_input("Anthropic API Key", type="password")
st.sidebar.caption(f"モデル: {MODEL}")

# ── 入力（タップ選択）──
grade = st.pills("学年", GRADES, selection_mode="single")
absence = st.pills("欠席の状況", ABSENCE, selection_mode="single")
backgrounds = st.pills("気になる背景（複数可）", BACKGROUNDS, selection_mode="multi")
text = st.text_area("相談内容・具体的な様子", height=110,
                    placeholder="例）3週間連続で欠席。電話には出るが学校の話になると口数が減る。家庭訪問すべきか迷う。")

go = st.button("対応のヒントを見る", type="primary")

if go:
    if not api_key:
        st.error("APIキーが未設定です（サイドバーに入力）。")
    elif not text.strip():
        st.warning("相談内容を入力してください。")
    else:
        parts = []
        if grade:
            parts.append(f"学年: {grade}")
        if absence:
            parts.append(f"欠席の状況: {absence}")
        if backgrounds:
            parts.append("背景: " + "、".join(backgrounds))
        ctx = ("\n".join(parts) + "\n\n") if parts else ""
        msg = ctx + f"相談:\n{text.strip()}"

        try:
            with st.spinner("一緒に考えています…"):
                r = ask_claude(api_key, msg)
        except ClaudeParseError as e:
            m = "応答が途中で切れました。相談を短くして再度お試しください。" \
                if e.stop_reason == "max_tokens" else "応答をうまく読み取れませんでした。再度お試しください。"
            st.error(m)
            with st.expander("原因確認用（返ってきた内容）"):
                st.caption(f"stop_reason: {e.stop_reason or '不明'}")
                st.code(e.raw or "(空)")
            st.stop()
        except Exception as e:
            st.error(f"エラー: {e}")
            st.stop()

        urg = r.get("urgency", "none")
        note = r.get("urgency_note", "")
        if urg == "high" and note:
            st.markdown(f'<div class="ban" style="background:#fef2f2;border:1px solid #fca5a5;color:#b91c1c;">🚨 <b>至急対応が必要な可能性</b><br>{esc(note)}</div>', unsafe_allow_html=True)
        elif urg == "elevated" and note:
            st.markdown(f'<div class="ban" style="background:#fffbeb;border:1px solid #fcd34d;color:#b45309;">⚠️ <b>注意して見守りたい</b><br>{esc(note)}</div>', unsafe_allow_html=True)

        def card_text(ic, tl, color, tint, body):
            st.markdown(f'<div class="card" style="background:{tint};border-left:4px solid {color};">'
                        f'<div class="hd"><span class="ic">{ic}</span><span class="tl" style="color:{color};">{tl}</span></div>'
                        f'<div class="tx">{esc(body)}</div></div>', unsafe_allow_html=True)

        def card_ul(ic, tl, color, tint, items, cls=""):
            lis = "".join(f"<li>{esc(x)}</li>" for x in items)
            st.markdown(f'<div class="card" style="background:{tint};border-left:4px solid {color};">'
                        f'<div class="hd"><span class="ic">{ic}</span><span class="tl" style="color:{color};">{tl}</span></div>'
                        f'<ul class="{cls}">{lis}</ul></div>', unsafe_allow_html=True)

        def card_ol(ic, tl, color, tint, items):
            lis = "".join(f"<li>{esc(x)}</li>" for x in items)
            st.markdown(f'<div class="card" style="background:{tint};border-left:4px solid {color};">'
                        f'<div class="hd"><span class="ic">{ic}</span><span class="tl" style="color:{color};">{tl}</span></div>'
                        f'<ol>{lis}</ol></div>', unsafe_allow_html=True)

        if r.get("assessment"):
            card_text("🧭", "見立て（BPS）", "#7c3aed", "#f5f3ff", r["assessment"])
        if r.get("basic_approach"):
            card_text("🌱", "基本方針", "#0f766e", "#f0fdfa", r["basic_approach"])
        if r.get("concrete_actions"):
            card_ul("💬", "声かけ・対応の例", "#ea580c", "#fff7ed", r["concrete_actions"])
        if r.get("collaboration"):
            card_ul("🤝", "つなぐ先", "#2563eb", "#eff6ff", r["collaboration"])
        if r.get("next_steps"):
            card_ol("👣", "次にとりたい行動", "#15803d", "#f0fdf4", r["next_steps"])
        if r.get("avoid"):
            card_ul("⚠️", "気を付けたいこと", "#d97706", "#fffbeb", r["avoid"], cls="xlist")

st.divider()
st.caption("※ 国（教育機会確保法・生徒指導提要・COCOLOプラン）と道教委（不登校対策プラン・支援ガイドブック）の考え方を参考にした補助ツールです。"
           "最終判断は本人・保護者を知る先生方がSC・SSW・管理職とチームで。虐待・自傷・いじめ被害の疑いは速やかに管理職・関係機関へ。"
           "個人が特定できる情報（氏名等）は入力しないでください。")
