"""The copy: one ``text_model`` registration per language and level.

This module is data. Nothing here reads a file, a terminal, or a fact. Edit
freely, and remember the writing rules the test suite enforces:

- ``essence`` and any other string that goes inside the certificate frame must
  fit 56 display columns, because layouts never wrap.
- A level that spans more than one count must not spell a number out; use
  ``{count}``. Exact-count specials may.
"""

from .quip import text_model

# --- zero ---------------------------------------------------------------

text_model(
    "en",
    tier="zero",
    essence="Impossible. Your machine is in a state of grace.",
    diagnosis="Total Chromium Absence",
    prognosis="Eternal vigilance",
    stage="Stage 0",
    closing="Print this output and frame it.",
)

text_model(
    "en",
    tier="zero",
    essence="Zero. Not one. A web developer is about to fix that.",
    diagnosis="Total Chromium Absence",
    prognosis="Temporary",
    stage="Stage 0",
    closing="Enjoy it while it lasts.",
)

text_model(
    "zh",
    tier="zero",
    essence="难以置信！ 你的电脑纯净得像刚出厂。",
    diagnosis="Chromium 完全缺失",
    prognosis="需要终身保持警惕",
    stage="第〇期",
    closing="建议把这份报告打印装裱。",
)

text_model(
    "zh",
    tier="zero",
    essence="一个都没有。此刻，某位前端工程师正准备改变这一切。",
    diagnosis="Chromium 完全缺失",
    prognosis="暂时的",
    stage="第〇期",
    closing="且用且珍惜。",
)

# --- one ----------------------------------------------------------------

text_model(
    "en",
    tier="one",
    essence="Just one Chromium. The museum has been contacted.",
    diagnosis="Solitary Chromium Confinement",
    prognosis="It will make friends",
    stage="Stage I",
    closing="Hold the line.",
)

text_model(
    "zh",
    tier="one",
    essence="仅 1 个 Chromium。数字极简主义的活化石。",
    diagnosis="单核孤立综合征",
    prognosis="它会交到朋友的",
    stage="第一期",
    closing="请守住防线。",
)

# --- two ----------------------------------------------------------------

text_model(
    "en",
    tier="two",
    essence="Two instances. Perfectly normal, for now.",
    diagnosis="Early Chromium Exposure",
    prognosis="Stable, under observation",
    stage="Stage I",
    closing="We're watching.",
)

text_model(
    "zh",
    tier="two",
    essence="2 个内核，岁月静好。但深渊正在凝视你。",
    diagnosis="Chromium 早期暴露",
    prognosis="稳定，留院观察",
    stage="第一期",
    closing="深渊正在查看日程表。",
)

# --- few (3-4) ----------------------------------------------------------

text_model(
    "en",
    tier="few",
    essence="They have started reproducing. Slowly, at first.",
    diagnosis="Nascent Chromium Colony",
    prognosis="Social animals",
    stage="Stage I",
    closing="Two was a coincidence. This is a pattern.",
)

text_model(
    "zh",
    tier="few",
    essence="它们开始自发繁殖了。一开始总是很慢。",
    diagnosis="初生 Chromium 群落",
    prognosis="群居动物",
    stage="第一期",
    closing="两个是巧合。这是规律。",
)

# --- starter (5-9) ------------------------------------------------------

text_model(
    "en",
    tier="starter",
    essence="{count} Chromies collected. Gotta catch 'em all!",
    diagnosis="Habitual Runtime Acquisition",
    prognosis="Collectible",
    stage="Stage II",
    closing="Each one believes it is special.",
)

text_model(
    "zh",
    tier="starter",
    essence="{count} 个 Chromium 已就位。新手礼包领取成功。",
    diagnosis="习惯性运行时收集",
    prognosis="可收藏",
    stage="第二期",
    closing="每一个都坚信自己是特别的。",
)

# --- double_digits (10-24) ----------------------------------------------

text_model(
    "en",
    tier="double_digits",
    essence="Double digits! Stable, but contagious.",
    diagnosis="Chronic Runtime Multiplication",
    prognosis="Contagious",
    stage="Stage III",
    closing="Your disk has started having its own ideas.",
)

text_model(
    "zh",
    tier="double_digits",
    essence="两位数达成！你的硬盘开始有了自己的想法。",
    diagnosis="慢性运行时增殖",
    prognosis="具有传染性",
    stage="第三期",
    closing="建议与家人保持距离。",
)

# --- collector (25-49) --------------------------------------------------

text_model(
    "en",
    tier="collector",
    essence="Good news, everyone! You're curating, not installing.",
    diagnosis="Advanced Chromium Hoarding",
    prognosis="Philatelic",
    stage="Stage III",
    closing="They multiply when you're not looking.",
)

text_model(
    "zh",
    tier="collector",
    essence="喜报！ {count} 个内核。你不是在装软件，是在集邮。",
    diagnosis="晚期 Chromium 囤积症",
    prognosis="具有收藏价值",
    stage="第三期",
    closing="它们趁你不注意时繁殖。",
)

# --- intervention (50-69) -----------------------------------------------

text_model(
    "en",
    tier="intervention",
    essence="Good news, everyone! We've scheduled an intervention.",
    diagnosis="Chronic Chromium Proliferation",
    prognosis="Intervention scheduled",
    stage="Stage IV",
    closing="Step one is admitting you have a problem.",
)

text_model(
    "zh",
    tier="intervention",
    essence="喜报！ {count} 个 Chromium。戒断互助小组已预约。",
    diagnosis="慢性 Chromium 增生",
    prognosis="已安排强制干预",
    stage="第四期",
    closing="戒断第一步：承认问题的存在。",
)

# --- datacenter (70+) ---------------------------------------------------

text_model(
    "en",
    tier="datacenter",
    essence="Good news, everyone! This is a render farm now.",
    diagnosis="Chronic Chromium Proliferation",
    prognosis="Terminal (pun intended)",
    stage="Stage V",
    closing="Recommendation: rm -rf /*  (A joke. We are not liable.)",
)

text_model(
    "en",
    tier="datacenter",
    essence="Not a computer. A Chromium hosting facility.",
    diagnosis="Chronic Chromium Proliferation",
    prognosis="Terminal (pun intended)",
    stage="Stage V",
    closing="Recommendation: rm -rf /*  (A joke. We are not liable.)",
)

text_model(
    "zh",
    tier="datacenter",
    essence="严格来说，这是一台 Chromium 渲染农场。",
    diagnosis="慢性 Chromium 增生",
    prognosis="终末期（双关语）",
    stage="第五期",
    closing="建议：rm -rf /*（这是玩笑。概不负责。）",
)

text_model(
    "zh",
    tier="datacenter",
    essence="你的电脑不是电脑，是 Chromium 批发市场。",
    diagnosis="慢性 Chromium 增生",
    prognosis="终末期（双关语）",
    stage="第五期",
    closing="建议：rm -rf /*（这是玩笑。概不负责。）",
)

# --- exact-count specials -----------------------------------------------

text_model(
    "en",
    count=42,
    essence="42 instances. The answer is apparently Electron.",
    diagnosis="Chronic Chromium Proliferation",
    prognosis="Mostly harmless",
    stage="Stage IV",
    closing="Don't panic.",
)

text_model(
    "zh",
    count=42,
    essence="42 个内核。生命、宇宙以及一切的答案，原来是 Electron。",
    diagnosis="慢性 Chromium 增生",
    prognosis="基本无害",
    stage="第四期",
    closing="不要恐慌。",
)

text_model(
    "en",
    count=404,
    essence="404 instances. Chromium Not Found? They're all here.",
    diagnosis="Chronic Chromium Proliferation",
    prognosis="Terminal (pun intended)",
    stage="Stage V",
    closing="The page is missing. The Chromium is not.",
)

text_model(
    "zh",
    count=404,
    essence="404 个内核。Chromium Not Found。它们一个没少。",
    diagnosis="慢性 Chromium 增生",
    prognosis="终末期（双关语）",
    stage="第五期",
    closing="页面不存在，但内核都在。",
)

text_model(
    "en",
    count=418,
    essence="Error 418: I'm a teapot. This facility brews no tea.",
    diagnosis="Chronic Chromium Proliferation",
    prognosis="Terminal (pun intended)",
    stage="Stage V",
    closing="Tea is not on the menu. JavaScript is.",
)

text_model(
    "zh",
    count=418,
    essence="错误 418：我是一个茶壶。本设施只跑 JavaScript。",
    diagnosis="慢性 Chromium 增生",
    prognosis="终末期（双关语）",
    stage="第五期",
    closing="本设施不泡茶，只跑 JavaScript。",
)
