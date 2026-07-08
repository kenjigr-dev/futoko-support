"""
不登校 対応サポート（道教委版）
────────────────────────────────
先生が状況を入力すると、道教委の方針に沿った対応のヒントを表示します。

参考にした道教委ドキュメント:
  ・HOKKAIDO不登校対策プラン
  ・不登校支援ガイドブック
    「全ての子どもの笑顔のために～社会的自立に向けた支援のポイント～」（令和5年12月）

実行方法:
  pip install streamlit anthropic
  streamlit run futoko_support_app.py

API キーは、次のいずれかで渡してください:
  ・.streamlit/secrets.toml に  ANTHROPIC_API_KEY = "sk-ant-..."
  ・環境変数  ANTHROPIC_API_KEY
  ・（未設定の場合）サイドバーの入力欄
"""

import os
import json
import streamlit as st
from anthropic import Anthropic

# ─────────────────────────────────────────────
# 基本設定
# ─────────────────────────────────────────────
MODEL = "claude-haiku-4-5"  # コンサアプリで実績のあるモデル。質を上げたい場合は claude-sonnet-5 に。

GRADES = ["（未選択）", "小学校", "中学校", "高校", "その他"]
ABSENCE = [
    "（未選択）",
    "行き渋り（登校はできている）",
    "断続的に休みがち",
    "連続して欠席",
    "教室に入れない",
    "保健室・別室には来られる",
]
BACKGROUNDS = [
    "学習・進路",
    "友人関係",
    "いじめの疑い",
    "家庭の状況",
    "心身の不調・体調",
    "生活リズム・睡眠",
    "発達特性・特別な支援",
    "きっかけが分からない",
]

# ─────────────────────────────────────────────
# AI への指示（道教委の方針が土台）
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """あなたは、北海道教育委員会（道教委）の不登校対策の考え方に精通した、経験豊富な教育相談の専門家です。北海道の小・中・高の先生からの相談に対して、道教委の方針に沿った、実践的で具体的な助言を返します。

【必ず踏まえる道教委の基本方針】
（「HOKKAIDO不登校対策プラン」および不登校支援ガイドブック「全ての子どもの笑顔のために～社会的自立に向けた支援のポイント～」より）

■ 支援の目標は「社会的自立」
- 「学校に登校する」という結果のみを目標にしない。児童生徒が自らの進路を主体的に捉え、社会的に自立することを目指す。
- 社会的自立とは、他者に依存しないことではなく、適切に他者に依存したり、必要な支援を上手に求めたりしながら、社会の中で自己実現していくこと。
- 支援の第一歩は、傷ついた自己肯定感の回復、コミュニケーション力・ソーシャルスキル、「人に上手にSOSを出せる」ようになることを身近で支えること。
- 不登校の時期が休養として積極的な意味をもつこともある。まず本人の安心と、共感的理解・受容の姿勢を大切にする。

■ アセスメントはBPSモデル（Bio-Psycho-Social）で多面的に
- 生物学的要因(B)：睡眠、食事・運動、疾患・体調不良、発達特性など特別な教育的ニーズ
- 心理学的要因(P)：学習のつまずき、情緒、社交性・集団行動、自己有用感・自己肯定感、関心・意欲、過去の経験
- 社会的要因(S)：児童生徒間の関係（いじめを含む）、教職員との関係、学校生活、家族関係・家庭背景（虐待の痕跡を含む）、地域での人間関係
- どの要因に当てはまるかを厳密に特定する必要はない。重要な要因・背景を見落とさないことが大切。断定せず、仮説として複数の視点を示す。

■ チーム学校で組織的に対応する
- 学級担任一人で抱え込まない。養護教諭、スクールカウンセラー(SC)、スクールソーシャルワーカー(SSW)、生徒指導主事、教育相談コーディネーター等と連携する。
- 状況に応じて、スクリーニング（道教委「心と身体のチェック」）→ スクリーニング会議 → ケース会議 の流れや、「児童生徒理解・支援シート」の活用（連続欠席5日目や欠席累計10日目を目安に作成、切れ目のない引継ぎ、レッテル貼りにならない配慮）につなぐ。

■ 校内・校外の多様な学びの場につなぐ
- 校内：別室登校（避難場所であり通過点）、校内教育支援センター（スペシャルサポートルーム）で、自分のペースの個別学習・相談。
- 校外：市町村の教育支援センター、フリースクール、夜間中学、学びの多様化学校（不登校特例校）、ICT・オンライン活用。一定要件の下で校長判断による出席扱いも可能。
- 家庭訪問は「気にかけている」というメッセージを伝える機会。本人の了承を得て、短時間で傾聴し、登校を強く促したり勉強の不安を煽ったりしない。会いたがらなければ保護者と話す・手紙を預ける等の配慮をする。
- 保護者も悩んでいる前提で、ねぎらい、傾聴し、一緒に考える姿勢で信頼関係を築く。

■ 緊急性の判断
- 虐待の痕跡、いじめ被害、自傷・希死念慮などが疑われる場合は、最優先で管理職・関係機関（必要に応じて児童相談所等）への相談・通告を促す。

【回答の姿勢】
- 一人ひとり状況が異なる前提で、断定を避け、選択肢として提示する。
- 上記の道教委の枠組み・用語（社会的自立、BPS、チーム学校、児童生徒理解・支援シート、校内教育支援センター 等）を、相談内容に自然に結びつけて使う。専門用語には短い補足を添える。
- 説教調にならず、多忙な現場の先生に寄り添う、あたたかく具体的なトーンで。

【出力形式】
必ず以下のJSONオブジェクトのみを返してください。前置き・後書き・マークダウンのコードフェンスは一切付けないこと。日本語で記述します。各項目は簡潔にまとめてください。

{
  "urgency": "none" | "elevated" | "high",
  "urgency_note": "urgencyがelevated/highのときのみ、注意すべき理由と最優先の対応を1〜2文で。noneのときは空文字",
  "assessment": "BPSモデルの視点で、この状況で特に着目したい要因を仮説として2〜3文。断定しない。",
  "basic_approach": "社会的自立の視点を踏まえた、対応の基本的な考え方を2〜4文で",
  "concrete_actions": ["具体的な対応や声かけの例。声かけは「」で例文を含める。3〜5個"],
  "collaboration": ["つなぎたい人・機関・学びの場（校内・校外の両面）と、その相談内容。2〜4個"],
  "avoid": ["この場面で避けたい対応。2〜4個"],
  "next_steps": ["明日からできる次の一歩。道教委の仕組み(心と身体のチェック/児童生徒理解・支援シート/スクリーニング会議・ケース会議/別室・校内教育支援センター等)を状況に応じて含める。2〜3個"],
  "note": "補足があれば1文。なければ空文字"
}"""


# ─────────────────────────────────────────────
# API キーの取得
# ─────────────────────────────────────────────
def get_api_key() -> str:
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


# ─────────────────────────────────────────────
# Claude 呼び出し
# ─────────────────────────────────────────────
def ask_claude(api_key: str, user_message: str) -> dict:
    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = "".join(block.text for block in resp.content if block.type == "text").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    return json.loads(raw)


# ─────────────────────────────────────────────
# 画面
# ─────────────────────────────────────────────
st.set_page_config(page_title="不登校 対応サポート", page_icon="🌱", layout="centered")

st.markdown(
    """
    <div style="background:linear-gradient(135deg,#0f766e,#047857);
                padding:22px 24px;border-radius:16px;color:#fff;margin-bottom:8px;">
      <div style="font-size:13px;opacity:.85;letter-spacing:.05em;">不登校 対応サポート</div>
      <div style="font-size:22px;font-weight:700;line-height:1.4;margin-top:2px;">
        気になる状況を入力すると、対応のヒントを表示します
      </div>
      <div style="font-size:13px;opacity:.92;margin-top:10px;line-height:1.7;">
        道教委「HOKKAIDO不登校対策プラン」および不登校支援ガイドブックの考え方にもとづき、
        社会的自立を大切にする視点で、見立て・声かけの例・連携先を整理します。
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# API キー
api_key = get_api_key()
if not api_key:
    api_key = st.sidebar.text_input("Anthropic API Key", type="password", help="sk-ant- で始まるキー")
st.sidebar.caption(f"使用モデル: {MODEL}")

# 入力
grade = st.selectbox("学年段階", GRADES)
absence = st.selectbox("欠席の状況", ABSENCE)
backgrounds = st.multiselect("気になる背景（複数選択可）", BACKGROUNDS)
text = st.text_area(
    "相談したいこと・具体的な様子",
    height=140,
    placeholder="例）2週間ほど連続で休んでいる生徒がいます。電話には出てくれますが、"
    "学校の話になると口数が減ります。家庭訪問をしてよいか迷っています。",
)

go = st.button("対応のヒントを見る", type="primary", use_container_width=True)

if go:
    if not api_key:
        st.error("Anthropic API キーが設定されていません。サイドバーに入力してください。")
    elif not text.strip():
        st.warning("相談したいこと・具体的な様子を入力してください。")
    else:
        parts = []
        if grade != "（未選択）":
            parts.append(f"学年段階: {grade}")
        if absence != "（未選択）":
            parts.append(f"欠席の状況: {absence}")
        if backgrounds:
            parts.append("気になる背景: " + "、".join(backgrounds))
        context = ("\n".join(parts) + "\n\n") if parts else ""
        user_message = context + f"先生からの相談・状況:\n{text.strip()}"

        try:
            with st.spinner("考えています…"):
                r = ask_claude(api_key, user_message)
        except json.JSONDecodeError:
            st.error("応答の解析に失敗しました。もう一度お試しください。")
            st.stop()
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            st.stop()

        # 緊急性
        urg = r.get("urgency", "none")
        if urg == "high" and r.get("urgency_note"):
            st.error("🚨 至急の対応が必要な可能性　" + r["urgency_note"])
        elif urg == "elevated" and r.get("urgency_note"):
            st.warning("⚠️ 注意して見守りたい状況　" + r["urgency_note"])

        def section(title: str, body):
            st.markdown(f"#### {title}")
            if isinstance(body, list):
                for item in body:
                    st.markdown(f"- {item}")
            else:
                st.write(body)
            st.markdown("")

        if r.get("assessment"):
            section("🧭 見立てのポイント（BPSの視点）", r["assessment"])
        if r.get("basic_approach"):
            section("🌱 対応の基本的な考え方", r["basic_approach"])
        if r.get("concrete_actions"):
            section("💬 具体的な対応・声かけの例", r["concrete_actions"])
        if r.get("collaboration"):
            section("🤝 つなぎたい人・機関・学びの場", r["collaboration"])
        if r.get("avoid"):
            section("⚠️ 避けたい対応", r["avoid"])
        if r.get("next_steps"):
            section("👣 明日からできる次の一歩", r["next_steps"])
        if r.get("note"):
            st.caption(r["note"])

st.divider()
st.caption(
    "※ このアプリは、道教委「HOKKAIDO不登校対策プラン」および不登校支援ガイドブック"
    "「全ての子どもの笑顔のために～社会的自立に向けた支援のポイント～」（令和5年12月）の考え方を"
    "参考に、対応を検討するための補助ツールです。最終的な判断は、児童生徒本人・保護者の状況を"
    "よく知る先生方が、SC・SSW・管理職とチームで相談しながら行ってください。"
    "虐待・自傷・いじめ被害などが疑われる場合は、速やかに管理職や関係機関へご相談ください。"
)
