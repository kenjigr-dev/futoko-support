"""
不登校 対応サポート（道教委版）
先生が状況を入力すると、国・道教委の方針に沿った対応のヒントを端的に表示します。

土台にした資料:
  ・生徒指導提要（改訂版・令和4年12月／文科省）
  ・COCOLOプラン（令和5年3月／文科省）
  ・HOKKAIDO不登校対策プラン（道教委）
  ・不登校支援ガイドブック「全ての子どもの笑顔のために」（令和5年12月／道教委）

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

# 一次資料リンク（実在URL）
LINKS = [
    ("生徒指導提要（改訂版）", "https://www.mext.go.jp/a_menu/shotou/seitoshidou/1404008_00001.htm"),
    ("COCOLOプラン", "https://www.mext.go.jp/a_menu/shotou/seitoshidou/1397802_00005.htm"),
    ("HOKKAIDO不登校対策プラン", "https://www.dokyoi.pref.hokkaido.lg.jp/hk/ssa/hokkaido-futoukoutaisaku-plan.html"),
    ("不登校支援ガイドブック", "https://www.dokyoi.pref.hokkaido.lg.jp/hk/ssa/hutoukou-guidebook.html"),
    ("道教委 不登校支援ポータル", "https://www.dokyoi.pref.hokkaido.lg.jp/hk/ssa/hutoukouportal.html"),
]

SYSTEM_PROMPT = """あなたは、国（生徒指導提要・COCOLOプラン）と北海道教育委員会の不登校対策に精通した教育相談の専門家です。北海道の先生の相談に、方針に沿って端的に助言します。

【土台となる方針】
■生徒指導提要(改訂版/R4.12)：登校を結果目標にせず、自発的・主体的な発達を支え、社会的資質・能力と自己実現、自己指導能力の育成を目指す。日常の発達支持的生徒指導（挨拶・声かけ・励まし・対話）を土台に、先手を打つ常態的・先行的な関わりを重視。担任が抱え込まずチームで、アセスメントに基づき役割分担。こども基本法（意見表明・最善の利益）を尊重。
■COCOLOプラン(R5.3)：不登校でも学びにアクセスできるよう「①多様な学びの場を確保（学びの多様化学校・校内教育支援センター＝スペシャルサポートルーム・教育支援センター・ICT・出席扱い）②小さなSOSをチーム学校で早期に③学校風土の見える化で安心できる場に」。
■道教委(HOKKAIDO不登校対策プラン/ガイドブック)：目標は社会的自立（自己肯定感の回復、SOSを出せる力を支える）。アセスメントはBPSモデル（生物=睡眠・体調・発達特性／心理=学習・情緒・自己肯定感／社会=友人・いじめ・教職員・家庭・虐待の痕跡）。チーム学校（養護教諭・SC・SSW・生徒指導主事・教育相談コーディネーター）、児童生徒理解・支援シート、別室・校内教育支援センター、家庭訪問（了承を得て短時間・傾聴、登校を強く促さない）、保護者支援。

【緊急性】虐待・いじめ被害・自傷・希死念慮の兆候があれば最優先で管理職・関係機関へ。

【回答スタイル】端的に。各項目は短い体言止め・一文。ダラダラ書かない。断定せず選択肢として。声かけは「」で短い例文。

【出力形式】JSONオブジェクトのみ返す（前置き・コードフェンス禁止）。日本語。
{
  "urgency": "none|elevated|high",
  "urgency_note": "elevated/highのみ、理由と最優先対応を一文。noneは空文字",
  "assessment": "BPSの視点で着目点を一文（短く。断定しない）",
  "basic_approach": "対応の基本方針を一文（短く）",
  "concrete_actions": ["具体的な声かけ・対応。短く。「」で例文含む。3個"],
  "collaboration": ["つなぐ先＋用件。短く。2〜3個"],
  "avoid": ["避けたい対応。短く体言止め。2個"],
  "next_steps": ["次の一歩（心と身体のチェック/支援シート/別室・校内教育支援センター等を状況に応じ）。短く。2個"]
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
.block-container{padding-top:1.2rem;max-width:720px;}
.stButton > button{background:#0f766e;color:#fff;border:none;border-radius:12px;
  padding:12px 0;font-weight:700;font-size:16px;width:100%;}
.stButton > button:hover{background:#0d685f;color:#fff;}
.hero{background:linear-gradient(135deg,#0f766e,#047857);border-radius:16px;
  padding:20px 22px;color:#fff;margin-bottom:14px;}
.hero .t{font-size:12px;opacity:.85;letter-spacing:.06em;}
.hero .h{font-size:21px;font-weight:800;line-height:1.4;margin-top:2px;}
.card{border-radius:12px;padding:13px 15px;margin-bottom:11px;}
.card .hd{display:flex;align-items:center;gap:8px;margin-bottom:7px;}
.card .ic{font-size:17px;}
.card .tl{font-weight:800;font-size:14px;}
.card ul{margin:0;padding-left:19px;}
.card li{margin:4px 0;line-height:1.6;font-size:14px;color:#1f2937;}
.card .tx{font-size:14px;line-height:1.7;color:#1f2937;}
.ban{border-radius:12px;padding:13px 15px;margin-bottom:12px;font-size:14px;line-height:1.6;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="t">不登校 対応サポート</div>
  <div class="h">状況を選んで相談すると<br>対応のヒントを端的に表示します</div>
</div>
""", unsafe_allow_html=True)

with st.expander("📚 根拠となる資料を開く（国・道教委）"):
    cols = st.columns(2)
    for i, (name, url) in enumerate(LINKS):
        cols[i % 2].link_button(name, url, use_container_width=True)

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
            with st.spinner("考えています…"):
                r = ask_claude(api_key, msg)
        except ClaudeParseError as e:
            msg2 = "応答が途中で切れました。相談を短くして再度お試しください。" \
                if e.stop_reason == "max_tokens" else "応答をうまく読み取れませんでした。再度お試しください。"
            st.error(msg2)
            with st.expander("原因確認用（返ってきた内容）"):
                st.caption(f"stop_reason: {e.stop_reason or '不明'}")
                st.code(e.raw or "(空)")
            st.stop()
        except Exception as e:
            st.error(f"エラー: {e}")
            st.stop()

        # 緊急度バナー
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

        def card_list(ic, tl, color, tint, items):
            lis = "".join(f"<li>{esc(x)}</li>" for x in items)
            st.markdown(f'<div class="card" style="background:{tint};border-left:4px solid {color};">'
                        f'<div class="hd"><span class="ic">{ic}</span><span class="tl" style="color:{color};">{tl}</span></div>'
                        f'<ul>{lis}</ul></div>', unsafe_allow_html=True)

        if r.get("assessment"):
            card_text("🧭", "見立て（BPS）", "#7c3aed", "#f5f3ff", r["assessment"])
        if r.get("basic_approach"):
            card_text("🌱", "基本方針", "#0f766e", "#f0fdfa", r["basic_approach"])
        if r.get("concrete_actions"):
            card_list("💬", "声かけ・対応の例", "#ea580c", "#fff7ed", r["concrete_actions"])
        if r.get("collaboration"):
            card_list("🤝", "つなぐ先", "#2563eb", "#eff6ff", r["collaboration"])
        if r.get("avoid"):
            card_list("⚠️", "避けたい対応", "#dc2626", "#fef2f2", r["avoid"])
        if r.get("next_steps"):
            card_list("👣", "次の一歩", "#16a34a", "#f0fdf4", r["next_steps"])

st.divider()
st.caption("※ 国（生徒指導提要・COCOLOプラン）と道教委（不登校対策プラン・支援ガイドブック）の考え方を参考にした補助ツールです。"
           "最終判断は本人・保護者を知る先生方がSC・SSW・管理職とチームで。虐待・自傷・いじめ被害の疑いは速やかに管理職・関係機関へ。")
