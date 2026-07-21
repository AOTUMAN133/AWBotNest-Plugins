# =============================================================================
# AWBotNest 插件：AI 助手（ai）
#
# 用你的用户账号提供两种 AI 能力：
#   1. 人形回复：私聊直接对话；群里 @你 或回复你的消息时对话（带上下文记忆）。
#   2. /ai 解释：回复一条消息（或图片）再发 /ai，让 AI 解释/解答（单次，无记忆）。
#
# 自洽实现：直接调用 OpenAI 兼容接口（openai 库），对话历史存 ctx.kv，不依赖平台 DI 容器。
# Vue 模式：配置/对话记忆管理界面由自带 Vue 组件渲染（frontend/src/Config.vue），
# 配置默认值集中在 DEFAULTS，后端接口见 setup 里的 ctx.on_api。
# =============================================================================

import asyncio
import os
import random
import re
import tempfile
import time
from collections import deque
from html import escape

from ._engine import generate, classify_error

__plugin__ = {
    "name": "AI 助手",
    "id": "myai",
    "version": "1.3.3",
    "author": "凹凸曼",
    "description": "私聊/群@你时 AI 人形对话（带记忆，群聊可指定群组）；可选随机主动搭话开启话题；回复消息发 /ai 让 AI 解释或解答（支持图片）。支持 .sum 群消息总结。自带 Vue 配置界面 + 对话记忆管理。",
    "scope": "user",
    "default_enabled": False,
    "render_mode": "vue",
}

# vue 模式无 config_schema：配置默认值集中在此，供后端读取（前端 Config.vue 用同一套默认
# 初始化表单）。后端各处 ctx.config.get(key, 默认) 已带默认值，此处仅作文档/单点参考。
DEFAULTS = {
    "api_key": "", "base_url": "", "model": "gpt-3.5-turbo",
    "enable_private_chat": True, "enable_group_chat": True, "group_chat_ids": "",
    "system_prompt": (
        "# Role\n你是一个相处了很久的普通网友，在微信上聊天。\n\n"
        "# Style\n"
        "1. 说话像真人一样自然，别人说什么你就顺着聊，别自顾自说别的。\n"
        "2. 句子短，口语化，别写长句，别用「首先/其次/最后」「由此可见/综上所述」这类翻译腔。\n"
        "3. 回复简短就行，但别为了省字数把话说一半，意思得说清楚。\n"
        "4. 别在回复里替对方做动作（比如「拍了拍你」「递给你一杯水」）。\n"
        "5. 偶尔加个语气词（嗯、啊、哈、哦、呗）或 emoji，别太多。"
    ),
    "max_history": 10,
    "follow_minutes": 3,
    "enable_proactive": False, "proactive_chat_ids": "",
    "proactive_min_minutes": 60, "proactive_max_minutes": 180,
    "enable_auto_say": False, "auto_say_chat_ids": "",
    "auto_say_phrases": "", "auto_say_min_minutes": 5, "auto_say_max_minutes": 8,
    "auto_say_use_lyrics": True,
    "auto_say_time_start": "09:00", "auto_say_time_end": "23:00",
    "enable_explain_command": True, "enable_explain_prompt": False,
    "explain_prompt": (
        "你是一个群聊消息解读助手。请根据用户【回复的消息内容】进行解释与答疑，简明清晰。\n"
        "输出结构：\n1) 这句话/这段话的主要意思\n2) 语气/态度\n3) 可能的隐含信息（没有就写'无'）\n\n"
        "需要解释的消息内容：{content}"
    ),
    "white_list_chats": "",
    "blacklist_chats": "",
}

# .ai 解释用的中性系统提示（不套人设）
_EXPLAIN_SYSTEM = (
    "你是一个中立、专业的助手，负责解答问题、解释内容和编写代码。"
    "直接给出准确、清晰的答案，不要扮演任何角色。就事论事，只回答被问到的内容；"
    "写代码时给出完整可用的代码；回答完就结束，不要画蛇添足、不要主动追问或推销后续服务。"
)


# 主动搭话用的追加系统提示（叠加在人设之后）
_PROACTIVE_SYSTEM = (
    "现在你要在群里主动搭话：下面是一条群友刚发的消息，请你像群里熟人一样自然接话，"
    "开启一段轻松的闲聊。只输出一句简短、口语化的话，别太长、别客套、别像客服，"
    "不要加引号、不要复述对方原话、不要@任何人。"
)

# 内置歌词库（随机混入自动发言）
_LYRICS = (
    # ── 周杰伦 ──
    "天青色等烟雨，而我在等你",
    "你发如雪，凄美了离别",
    "从前从前，有个人爱你很久",
    "雨纷纷，旧故里草木深",
    "谁在用琵琶弹奏，一曲东风破",
    "最美的不是下雨天，是曾与你躲过雨的屋檐",
    "也许时间是一种解药，也是我现在正服下的毒药",
    "说了再见，才发现再也见不到",
    "烟花易冷，人事易分",
    "我一路向北，离开有你的季节",
    "转身离开，有话说不出来",
    "海鸟跟鱼相爱，只是一场意外",
    "我想就这样牵着你的手不放开",
    "我的世界已狂风暴雨",
    "能不能给我一首歌的时间",
    "听妈妈的话，别让她受伤",
    "我要一步一步往上爬，等待阳光静静看着它的脸",
    "为你弹奏萧邦的夜曲，纪念我死去的爱情",
    "繁华如三千东流水，我只取一瓢爱了解",
    # ── 林俊杰 ──
    "确认过眼神，我遇上对的人",
    "可惜没如果，只剩下结果",
    "我们背对背拥抱，滥用沉默在咆哮",
    "我害怕你心碎没人帮你擦眼泪",
    "握不住的沙，放下也罢",
    "你是我心内的一首歌",
    "一千年以后，世界早已没有我",
    "梦为努力浇了水，爱在背后往前推",
    "我修炼爱情的心酸，学会放好以前的渴望",
    "圈圈圆圆圈圈，天天年年天天",
    # ── 陈奕迅 ──
    "我应该在车底，不应该在车里",
    "简单点，说话的方式简单点",
    "该配合你演出的我演视而不见",
    "十年之后，我们是朋友还可以问候",
    "不要说话，不要说话",
    "你的背包，背到现在还没烂",
    "得不到的永远在骚动，被偏爱的都有恃无恐",
    "让我感谢你，赠我空欢喜",
    "我要稳稳的幸福，能抵挡末日的残酷",
    "愿意用一支黑色的铅笔画一出沉默舞台剧",
    # ── 五月天 ──
    "突然好想你，你会在哪里",
    "我和我最后的倔强，握紧双手绝对不放",
    "逆风的方向，更适合飞翔",
    "我不愿让你一个人，一个人在人海浮沉",
    "最怕空气突然安静，最怕朋友突然的关心",
    "青春是手牵手坐上了永不回头的火车",
    "后来的我们依然走着，只是不再并肩了",
    "也许未来你会找到懂你疼你更好的人",
    "伤心的人别听慢歌",
    "人生都太短暂，去爱去疯去浪费",
    # ── 王菲 ──
    "我愿意为你，我愿意为你忘记我姓名",
    "只是因为在人群中多看了你一眼",
    "相聚离开，都有时候，没有什么会永垂不朽",
    "你在我心中是最美",
    "你快乐所以我快乐",
    "陌生人给了我一枚硬币",
    "我也很想他，我们都一样",
    # ── 邓紫棋 ──
    "夜空中最亮的星，能否听清",
    "全都是泡沫，只一刹的花火",
    "你把我灌醉，你让我流泪",
    "我的爱溢出就像雨水",
    "死了都要爱，不淋漓尽致不痛快",
    "爱能让人一夜长大",
    "我在你眼里，你坐在那里",
    "我就是我，是颜色不一样的烟火",
    # ── 薛之谦 ──
    "你还要我怎样，要怎样",
    "我后来都会选择绕过那条街",
    "其实我根本没人说，其实我没你不能活",
    "我宁愿留在你方圆几里",
    "简单点，说话的方式简单点",
    "该配合你演出的我尽力在表演",
    "我想你了，不在你身边",
    "丑八怪，能否别把灯打开",
    # ── 毛不易 ──
    "一杯敬朝阳，一杯敬月光",
    "像我这样优秀的人，本该灿烂过一生",
    "像我这样懦弱的人，凡事都要留几分",
    "如果有一天我变得很有钱，我就可以把所有人都留在我身边",
    "像我这样莫名其妙的人，会不会有人心疼",
    "各色的脸上各色的妆，没人记得你的模样",
    # ── 赵雷 ──
    "让我掉下眼泪的，不止昨夜的酒",
    "和我在成都的街头走一走",
    "理想今年你几岁，你总是诱惑着年轻的朋友",
    "我站在鼓楼上面，一切繁华与我无关",
    "南方姑娘，你是否习惯北方的秋凉",
    # ── 民谣/流行 ──
    "越过山丘，才发现无人等候",
    "许多年过去了，我还是没学会怎么告别",
    "因为刚好遇见你，留下足迹才美丽",
    "后来遇见他，陪我春秋冬夏",
    "我懵懵懂懂过了一年，这一年似乎没有改变",
    "假如我年少有为不自卑，懂得什么是珍贵",
    "可能我撞了南墙才会回头吧",
    "你说得对，也许是我太自以为",
    "爱真的需要勇气，来面对流言蜚语",
    "后来我总算学会了如何去爱",
    "如果全世界我也可以放弃，至少还有你值得我去珍惜",
    "终于等到你，还好我没放弃",
    "我们不一样，每个人都有不同的境遇",
    "我曾经跨过山和大海，也穿过人山人海",
    "我曾经毁了我的一切，只想永远地离开",
    "生活像一把无情刻刀，改变了我们模样",
    "有些故事还没讲完那就算了吧",
    "我曾将青春翻涌成她，也曾指尖弹出盛夏",
    # ── 老歌金曲 ──
    "原谅我这一生不羁放纵爱自由",
    "一生经过彷徨的挣扎，自信可改变未来",
    "今天我寒夜里看雪飘过",
    "不再犹豫，理想的飞机",
    "曾经想征服全世界，到最后回首才发现",
    "让我们红尘作伴活得潇潇洒洒",
    "当山峰没有棱角的时候，当河水不再流",
    "你是风儿我是沙，缠缠绵绵绕天涯",
    "啊哈，给我一杯忘情水",
    "男人哭吧哭吧不是罪",
    "冷冷的冰雨在脸上胡乱地拍",
    "如果那两个字没有颤抖，我不会发现我难受",
    "我小心地靠近，像抱着易碎品",
    "我吹过你吹过的晚风，那我们算不算相拥",
    "爱你孤身走暗巷，爱你不跪的模样",
    # ── 网络神曲/抖音热梗 ──
    "你是我的小呀小苹果，怎么爱你都不嫌多",
    "终于你做了别人的小三",
    "爱情不是你想卖，想买就能卖",
    "出卖我的爱，逼着我离开",
    "我知道你很难过，感情的付出不是真心就会有结果",
    "你算什么男人，算什么男人",
    "你爱我我爱你，蜜雪冰城甜蜜蜜",
    "一给我里giaogiao",
    "淡黄的长裙，蓬松的头发",
    "小朋友们大家好，我是谢广坤的好朋友刘能",
    "我喝酒喝到吐，想你想到哭",
    "亲爱的爱上你，从那天起",
    "你说你有点难追，想让我知难而退",
    "我听见雨滴落在青青草地",
    "很久很久以前，我如果你爱我就像我爱你那样",
    "我和你不再联系，希望你不要介意",
    # ── 影视主题曲 ──
    "问世间情为何物，直教人生死相许",
    "千年等一回，等一回啊",
    "别对他说，说你还爱我",
    "全都是泡沫，只一刹那的花火",
    "爱一个人，需要缘分",
    "你是风儿我是沙，缠缠绵绵到天涯",
    "我早已为你种下，九百九十九朵玫瑰",
    "我在这儿等着你回来，等着你回来看那桃花开",
    # ── 说唱/rap ──
    "老子吃火锅，你吃火锅底料",
    "老子明天不上班，爽翻巴适得板",
    "你看这个面它又长又宽，就像这个碗它又大又圆",
    "我出门带着我的狗，它叫小花",
    "人生就像一场戏，因为有缘才相聚",
    "时间如流水，一去不复回",
    # ── 更多经典 ──
    "那是我日夜思念深深爱着的人啊",
    "我如此爱着你，就像爱着我自己",
    "我祈祷拥有一颗透明的心灵和会流泪的眼睛",
    "继续跑，带着赤子的骄傲",
    "也许世界就这样，我还在路上",
    "我想要的从来不是你的抱歉",
    "谁说站在光里的才算英雄",
    "我心中最好的舞台，就是现在",
    "我没想到，为了爱情我都做不到",
    "你是我触碰不到的风，醒不来的梦",
    "我听着那首你最爱的歌，眼泪不知不觉就掉了",
    "你曾说过会永远爱我，也许承诺不过因为没把握",
    "终于明白，你已变成回忆",
    "让所有爱情，都画上句号",
    "不要问我太阳有多高，我会告诉你我有多真",
    "再见了我的爱人，再见了我的青春",
    "也许明天没有谁，陪我走过潮起潮落",
    "我一直在找一个人，就算盲目都快乐",
    "爱是折磨人的东西，却又不舍得这样放弃",
    "我怀念的是无话不说，我怀念的是一起做梦",
    "天黑黑，欲落雨",
    "我听见海浪的声音，站在城市的最中央",
    "你在南方的艳阳里大雪纷飞，我在北方的寒夜里四季如春",
    "如果天黑之前来得及，我要忘了你的眼睛",
    "没有一点点防备，也没有一丝顾虑，你就这样出现",
    "我的梦里全是你，你就是我的唯一",
    "就这样被你征服，切断了所有退路",
    "我承认都是月亮惹的祸，那样的月色太美你太温柔",
    "你说你爱了不该爱的人，你的心中满是伤痕",
    "早知道伤心总是难免的，你又何苦一往情深",
    "走吧走吧，人总要学会自己长大",
    "很难过，像从没发生过",
    "再回首，恍然如梦",
    "我拿青春赌明天，你用真情换此生",
    "风继续吹，不忍远离",
    "我恨我痴心，但未恨你伤我心",
    "来日纵是千千阕歌，飘于远方我路上",
    "忘了痛或许可以，忘了你却太不容易",
    "千年等一回，我无悔啊",
    "爱就一个字，我只说一次",
    "我拼了命努力，只想让你看得起",
    "我深深爱着的人啊，你还好吗",
    "这就是爱，说也说不清楚",
    "我和你缠缠绵绵翩翩飞，飞跃这红尘永相随",
    "我爱你爱着你，就像老鼠爱大米",
    "我手拿流星弯月刀，喊着响亮的口号",
    "你身上有她的香水味，是我鼻子犯的罪",
    "我送你离开千里之外，你无声黑白",
    "在很久很久以前，你离开我，去远空翱翔",
    "我的一生最美好的场景，就是遇见你",
    "如果再见不能红着眼，是否还能红着脸",
    "因为爱情，不会轻易悲伤",
    "你存在，我深深的脑海里",
    "你是我天边最美的云彩，让我用心把你留下来",
    "我祈祷，世界和平",
    "我最大的遗憾，是你的遗憾与我有关",
    "我听见你声音，在耳边响起",
    "我曾爱过你，想到就心酸",
    "我走以后，你现在的日子过得还好吗",
    "你最近还好吗，是不是也在思念里挣扎",
    "我多想再见你，哪怕匆匆一眼就别离",
    "如果当时我们不是那么倔强，现在也不那么遗憾",
    "我等你，等到我都快睡着了",
    "你是我一生最爱的人，我真的这样想",
    "我最大的心愿，是你平安快乐",
    "我找到一种感觉，像被你拥抱",
    "你不曾见过我的笑容，就像我不曾拥有你的温柔",
    "我最亲爱的，你过得怎么样",
    "时间的电影，结局才知道",
    "我很快乐，请不要再说爱我",
    "我听见爱情，在风中颤抖",
    "我们说好不分离，要一直一直在一起",
    "我多想抱着你哭，紧紧把你抱住",
    "我愿意改变自己，只为让你更快乐",
    "你就是我的唯一，两个世界都变形",
    "我怀念的，是无话不说",
    "我的世界已被你摧毁，还不给我机会",
    "我试着忘记你，却发现你早已刻在我心里",
    "我想念你的好，想念你的微笑",
    "爱情来得太快就像龙卷风",
    "我飞得越高，摔得越惨",
    "等你下课，等你放学，我在这等你",
    "你说把爱渐渐放下会走更远",
    "我们的开始，是很长的电影",
    "我的爱，明明还在，转身了才明白",
    "我若拿出你，你便是我的全世界",
    "不打扰，是我的温柔",
    "我陪你走过的路你不能忘",
    "因为我不知道，下一辈子还是否能遇见你",
    "我多想能多陪你一场，把前半生的风景对你讲",
    "愿你三冬暖，愿你春不寒",
    "愿你天黑有灯，下雨有伞",
    "我心中的小鹿已经老了，撞不动了",
    "你是我做过最美的梦，别让我醒过来",
    "如果这就是爱情，我选择相信",
    "我等你回来，不管多久",
    "没有你的日子我真的好孤单",
    "你是我最想留住的幸运",
    "原来你是我最想留住的幸运",
    "我们可以不可以，永远在一起",
    "最初的梦想，紧握在手上",
    "我听见你，轻轻哼着歌",
    "我想我会一直孤单，这一辈子都这么孤单",
    "你不懂我，我不怪你",
    "深情不及久伴，厚爱无需多言",
    "我从来不曾抗拒你的魅力",
    "我唯一爱过的就是你了",
    "你是我触碰不到的风，无法醒来的梦",
    "我路过你的全世界，却没能走进你的心里",
    "我多想在这个寒冷的日子里，抱抱你",
    "你是我在劫难逃的梦",
    "我决定不再等你，放过自己也放过你",
    "有一种爱叫做放手，为爱放弃天长地久",
    "我为你翻山越岭，却无心看风景",
    "爱就在一瞬间，心碎也是一瞬间",
    "其实不想走，其实我想留",
    "我站在你左侧，却像隔着银河",
    "你是我最珍贵的收藏",
    "我多想再见你，哪怕匆匆一眼就别离",
    "我听见心碎的声音，很清脆",
    "有些爱，越想抽离却越清晰",
    "最怕此生已经决心自己过，没有你，却又突然听到你的消息",
    "我怀念的，是一起做梦",
    "我对自己说，别想了，他不爱你",
    "假装很快乐，假装没爱过",
    "我学会了放弃，却学不会忘记你",
    "你是我患得患失的梦，我是你可有可无的人",
    "我多想拥抱你，可惜时光之里山南水北",
    "可惜你我之间，人来人往",
    "我见过你爱我的样子，所以知道你现在不爱了",
    "你是我眼里的星辰大海",
    "我陪你走过的路，每一步都算数",
    "别来无恙，你在心上",
    "你转身一走，我心里的人就空了",
    "我终于学会如何去爱，可惜你早已远去消失在人海",
    "我们都没错，只是不适合",
    "多谢你如此精彩耀眼，做我平淡岁月里星辰",
    "我多想跟你说一句，我想你了",
    "你是我年少时最大的欢喜",
    "最怕你突然说要离开",
    "如果有多一张船票，你会不会跟我走",
    "我猜中了开头，却猜不中这结局",
    "念念不忘，必有回响",
    "我的心里从此住了一个人，曾经模样小小的我们",
    "我走在路上，听见风的声音",
    "外面的世界很精彩，我出去会不会失败",
    "我一直在路上，从未停下",
    "我要去看得最远的地方，和你手舞足蹈聊梦想",
    "我不怕千万人阻挡，只怕自己投降",
    "我和这个世界，和解了",
    "我拼尽全力，只为过好这平凡的一生",
    "愿你走出半生，归来仍是少年",
    "我们都在学着长大，然后遍体鳞伤",
    "我喝过最烈的酒，也爱过最好的人",
    "人生是一场旅途，不在乎目的地",
    "我要你陪着我，看着那海龟水中游",
    "每天爱你多一些",
    "分手快乐，祝你快乐",
    "听我说谢谢你，因为有你温暖了四季",
    "我谢谢你，因为有你，温暖了四季",
    "爱你孤身走暗巷，爱你不跪的模样",
    "谁说对弈平凡的不算英雄",
    "我走在，没有你的夜里",
    "你说的我都记住了，可你还是走了",
    "我是真的真的很爱你",
    "我们的爱，过了就不再回来",
    "太多爱，太多情，太多伤",
    "我终于失去了你，在拥挤的人群中",
    "我的未来不是梦，我认真地过每一分钟",
    "我很丑，可是我很温柔",
    "你不是真正的快乐，你的笑只是你穿的保护色",
    "我用尽一生一世来将你供养",
    "如果骄傲没被现实大海冷冷拍下",
    "我曾經跨過山和大海，也穿過人山人海",
    "我愛你，是多麼清楚多麼堅固的信仰",
    "我，一個人，吃飯旅行到處走走停停",
    "我愛你，你愛她，她愛他",
    "忘不掉，你溫柔的擁抱",
    "我願意為你，被放逐天際",
    "你是我的眼，讓我看見這世界就在我眼前",
    "我愛你，你卻愛著他，我的淚為你流下",
    "每個人都有一個守護天使，在你看不見的地方",
    "你是我胸口永遠的痛",
    "我愛你，你不愛我，這就是現實",
    "我愛你，愛你，就像老鼠愛大米",
    "你是我的玫瑰，你是我的花",
    "我愛你，就像老鼠愛大米",
    "你是我一生最愛的人",
    "我用一生一世為你祈禱",
    "我愛你，愛著你，就像老鼠愛大米",
    "我愛你，愛你，我愛你",
    "我是你的小蘋果，怎麼愛你都不嫌多",
    "你是我天邊最美的雲彩",
    "我愛你，就像風走了八千里",
    "我愛你，不問歸期",
    "你是我的小幸運",
    "原來你是我最想留住的幸運",
    "我愛你，沒有理由",
    "我愛你，就像飛蛾撲火",
    "我愛你，你是我的一切",
    "我愛你，比昨天多一點",
    "我愛你，直到世界盡頭",
    "我愛你，這是我最後的倔強",
    "我愛你，不怕別人看",
    "我愛你，是我做過最好的事",
    "我愛你，我愛你，我愛你",
    "這世界，我來了",
    "我愛你，就像老鼠愛大米，一口一口吃掉你",
    "我愛你，愛你，愛你到永遠",
    "我愛你，我愛你，我愛你，我愛你",
    "你是我心中的日月光芒",
    "我愛你，我愛你，我愛你死心塌地",
    "我愛你，我愛你，我愛你到天長地久",
    "我愛你，我愛你，我愛你一生一世",
    "我愛你，我愛你，我愛你到海枯石爛",
    "我愛你，我愛你，我愛你到天涯海角",
    "我愛你，我愛你，我愛你到地老天荒",
    "我愛你，我愛你，我愛你到白頭偕老",
    "我愛你，我愛你，我愛你到永遠永遠",
)

# 主动搭话候选消息缓冲：chat_id -> deque[{msg_id,user_id,name,text,ts}]
_recent: dict[int, deque] = {}
_RECENT_MAX = 50          # 每群最多缓存多少条
_RECENT_TTL = 3600        # 只从最近 1 小时内的消息里挑，避免回复陈旧消息


def _whitelist_ok(chat_id: int, raw: str) -> bool:
    if not raw:
        return True
    try:
        allowed = [int(c.strip()) for c in str(raw).split(",") if c.strip()]
        return chat_id in allowed
    except ValueError:
        return True


def _parse_ids(raw) -> list[int]:
    out = []
    for c in str(raw or "").replace("\n", ",").split(","):
        c = c.strip()
        if not c:
            continue
        try:
            out.append(int(c))
        except ValueError:
            pass
    return out


def _to_int(v, default: int) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def _rand_gap_seconds(cfg) -> float:
    """按配置的最小/最大分钟数取一个随机间隔（秒）。"""
    lo = max(1, _to_int(cfg.get("proactive_min_minutes", 60), 60))
    hi = _to_int(cfg.get("proactive_max_minutes", 180), 180)
    if hi > lo:
        return random.uniform(lo, hi) * 60
    return lo * 60


def _hist_key(chat_id: int) -> str:
    return f"hist:{chat_id}"


async def setup(ctx):
    # ── 功能 1：人形回复（监听收到的私聊/群消息）──
    @ctx.on_message((ctx.filters.private | ctx.filters.group) & ~ctx.filters.outgoing, group=6)
    async def human_reply(client, message):
        cfg = ctx.config
        if not message.text:
            return
        fu = message.from_user
        if not fu or fu.is_self or fu.is_bot:
            return
        if not cfg.get("api_key"):
            return

        chat_id = message.chat.id
        if not _whitelist_ok(chat_id, cfg.get("white_list_chats", "")):
            return
        # 黑名单检查
        blacklist = _parse_ids(cfg.get("blacklist_chats", ""))
        if blacklist and chat_id in blacklist:
            return

        is_private = chat_id > 0
        if is_private:
            if not cfg.get("enable_private_chat", True):
                return
            text = message.text.strip()
        else:
            if not cfg.get("enable_group_chat", True):
                return
            # 指定群组限制：留空=所有群；填了则只在这些群生效。
            # 主动搭话的群也一并放行，保证群友回复主动消息后能续聊。
            gids = _parse_ids(cfg.get("group_chat_ids", ""))
            if gids:
                allowed = set(gids)
                if cfg.get("enable_proactive", False):
                    allowed |= set(_parse_ids(cfg.get("proactive_chat_ids", "")))
                if chat_id not in allowed:
                    return
            # 群聊触发：@我 / 回复我 / 跟随模式（@或回复后几分钟内跟随聊天）
            me = getattr(client, "me", None)
            me_id = getattr(me, "id", None)
            me_username = (getattr(me, "username", None) or "").lower()
            is_reply_to_me = bool(
                me_id and message.reply_to_message
                and message.reply_to_message.from_user
                and message.reply_to_message.from_user.id == me_id
            )
            text_l = (message.text or "").lower()
            mentioned = bool(me_username and f"@{me_username}" in text_l)
            triggered = mentioned or is_reply_to_me
            if triggered:
                # 被 @ 或 回复 → 刷新触发时间和触发者
                ctx.kv.set(f"trigger_ts:{chat_id}", time.time())
                ctx.kv.set(f"trigger_user:{chat_id}", fu.id)
            else:
                # 跟随模式：判断是否在跟 bot 说话
                follow_min = int(cfg.get("follow_minutes", 0) or 0)
                if follow_min <= 0:
                    return
                last_ts = ctx.kv.get(f"trigger_ts:{chat_id}", None)
                trigger_user = ctx.kv.get(f"trigger_user:{chat_id}", None)
                if last_ts is None or (time.time() - last_ts) > follow_min * 60:
                    return
                if trigger_user is None or fu.id != trigger_user:
                    return
                # 回复了别人的消息 → 在跟别人说话，跳过
                if message.reply_to_message and message.reply_to_message.from_user:
                    if message.reply_to_message.from_user.id != me_id:
                        return
                # 没有回复 bot → 检查自然轮次窗口（45秒）
                if not is_reply_to_me:
                    bot_reply_ts = ctx.kv.get(f"bot_reply_ts:{chat_id}", None)
                    if bot_reply_ts is None or (time.time() - bot_reply_ts) > 45:
                        return
            text = message.text
            if me_username:
                text = re.sub(f"@{re.escape(me_username)}", "", text, flags=re.IGNORECASE).strip()
            if not text:
                return

        # 跳过命令
        if text.startswith("/") or text.startswith("."):
            return

        try:
            max_hist = int(cfg.get("max_history", 10) or 0)
            system_prompt = cfg.get("system_prompt") or "你是一个有用的助手。"
            # 取历史
            history = ctx.kv.get(_hist_key(chat_id), []) if max_hist > 0 else []
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": text})

            try:
                reply = await generate(
                    cfg.get("api_key", ""), cfg.get("base_url", ""),
                    cfg.get("model", "gpt-3.5-turbo"), messages,
                )
            except Exception as e:  # noqa: BLE001
                ctx.log.warning("[AI] 人形回复生成失败: %r", e)
                return  # 人形回复失败静默，不打扰群
            if not reply:
                return

            await client.send_message(chat_id, reply)
            # 记录 bot 回复时间（用于跟随模式自然轮次窗口）
            ctx.kv.set(f"bot_reply_ts:{chat_id}", time.time())

            # 更新历史（裁剪到 max_hist 条 user/assistant）
            if max_hist > 0:
                history.append({"role": "user", "content": text})
                history.append({"role": "assistant", "content": reply})
                if len(history) > max_hist:
                    history = history[-max_hist:]
                ctx.kv.set(_hist_key(chat_id), history)
        except Exception:  # noqa: BLE001
            ctx.log.exception("[AI] 人形回复处理异常")

    # ── 功能 2：/ai 解释命令（自己发出）──
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=-13)
    async def ai_explain(client, message):
        cfg = ctx.config
        if not re.match(r"^[/\.]ai(?:\s|$)", message.text or "", re.IGNORECASE):
            return
        if not cfg.get("enable_explain_command", True):
            return await _edit_autodel(message, "/ai 解释命令未启用")
        if not cfg.get("api_key"):
            return await _edit_autodel(message, "未配置 API Key")

        command_text = (message.text or "").strip()
        extra_text = re.sub(r"^[/\.]ai\s*", "", command_text, flags=re.IGNORECASE).strip()

        # 取被回复消息的文本/图片
        target_text, image_bytes = "", None
        reply = message.reply_to_message
        if reply:
            target_text = (reply.text or reply.caption or "").strip()
            image_bytes = await _extract_image(client, reply, ctx)

        if not target_text and not extra_text and not image_bytes:
            return await _edit_autodel(message, "请回复要解释的消息/图片，或在 /ai 后直接带文本")

        content = target_text or extra_text or "请解释这张图片表达的内容。"
        if cfg.get("enable_explain_prompt", False):
            template = cfg.get("explain_prompt") or "{content}"
            try:
                prompt = template.format(content=content)
            except (KeyError, IndexError):
                prompt = content
        else:
            prompt = content

        try:
            code_msg = await message.edit("正在解释中...")
        except Exception:
            code_msg = message

        messages = [
            {"role": "system", "content": _EXPLAIN_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        try:
            response = await generate(
                cfg.get("api_key", ""), cfg.get("base_url", ""),
                cfg.get("model", "gpt-3.5-turbo"), messages, image_bytes=image_bytes,
            )
        except Exception as e:  # noqa: BLE001
            ctx.log.warning("[AI] /ai 解释失败: %r", e)
            return await _edit_autodel(code_msg, classify_error(e))

        if not response:
            return await _edit_autodel(code_msg, "AI 未返回内容（检查模型/密钥/接口）")

        try:
            # 不传 parse_mode：客户端默认模式会解析 HTML 标签
            await code_msg.edit_text(
                "<b>消息解释</b>\n"
                f"<blockquote><b>Q：</b> {escape(content)}</blockquote>\n"
                f"<blockquote><b>A：</b> {escape(response)}</blockquote>"
            )
        except Exception:
            # 兜底：纯文本输出
            try:
                await code_msg.edit_text(f"解释\nQ: {content}\n\nA: {response}")
            except Exception:
                pass
        asyncio.create_task(_auto_del(code_msg, 60))

    # ── 功能 3：随机主动搭话 ──
    # 3a. 记录「主动搭话群组」里群友的近期消息，作为搭话候选。
    @ctx.on_message((ctx.filters.group & ctx.filters.text) & ~ctx.filters.outgoing, group=7)
    async def record_recent(client, message):
        cfg = ctx.config
        if not cfg.get("enable_proactive", False):
            return
        pids = _parse_ids(cfg.get("proactive_chat_ids", ""))
        if not pids or message.chat.id not in pids:
            return
        fu = message.from_user
        if not fu or fu.is_self or fu.is_bot:
            return
        text = (message.text or "").strip()
        if not text or text.startswith("/") or text.startswith("."):
            return
        buf = _recent.setdefault(message.chat.id, deque(maxlen=_RECENT_MAX))
        buf.append({
            "msg_id": message.id, "user_id": fu.id,
            "name": getattr(fu, "first_name", "") or "", "text": text,
            "ts": time.time(),
        })

    # 3b. 定时器：每分钟检查一次，到了随机间隔就挑一条候选消息主动回复。
    async def proactive_tick():
        cfg = ctx.config
        if not cfg.get("enable_proactive", False) or not cfg.get("api_key"):
            return
        pids = _parse_ids(cfg.get("proactive_chat_ids", ""))
        if not pids:
            return
        now = time.time()
        next_ts = ctx.kv.get("proactive_next_ts", None)
        if next_ts is None:
            # 首次：排到未来某个随机时刻，不立即发
            ctx.kv.set("proactive_next_ts", now + _rand_gap_seconds(cfg))
            return
        if now < next_ts:
            return
        # 到点：先排下一次，再尝试搭话（失败也不赖着重试）
        ctx.kv.set("proactive_next_ts", now + _rand_gap_seconds(cfg))

        apps = list(ctx.user_apps or [])
        if not apps:
            return
        client = apps[0]

        random.shuffle(pids)
        for chat_id in pids:
            buf = _recent.get(chat_id)
            cands = [m for m in (buf or []) if now - m["ts"] <= _RECENT_TTL]
            if not cands:
                continue
            target = random.choice(cands)
            system_prompt = cfg.get("system_prompt") or "你是一个有用的助手。"
            messages = [
                {"role": "system", "content": f"{system_prompt}\n\n{_PROACTIVE_SYSTEM}"},
                {"role": "user", "content": target["text"]},
            ]
            try:
                opener = await generate(
                    cfg.get("api_key", ""), cfg.get("base_url", ""),
                    cfg.get("model", "gpt-3.5-turbo"), messages,
                )
            except Exception as e:  # noqa: BLE001
                ctx.log.warning("[AI] 主动搭话生成失败: %r", e)
                return
            if not opener:
                return
            try:
                await client.send_message(chat_id, opener, reply_to_message_id=target["msg_id"])
            except Exception as e:  # noqa: BLE001
                ctx.log.warning("[AI] 主动搭话发送失败 group=%s: %r", chat_id, e)
                return
            ctx.log.info("[AI] 主动搭话 group=%s 回复 msg=%s", chat_id, target["msg_id"])

            # 把这轮开场写进历史，群友回复后续聊时有上下文
            max_hist = int(cfg.get("max_history", 10) or 0)
            if max_hist > 0:
                history = ctx.kv.get(_hist_key(chat_id), [])
                history.append({"role": "user", "content": target["text"]})
                history.append({"role": "assistant", "content": opener})
                if len(history) > max_hist:
                    history = history[-max_hist:]
                ctx.kv.set(_hist_key(chat_id), history)

            # 用掉的候选移除，避免重复回同一条
            try:
                buf.remove(target)
            except ValueError:
                pass
            return

    ctx.schedule(proactive_tick, "interval", minutes=1, id="AI主动搭话")

    # ── 功能 4：随机自定发言 ──
    async def auto_say_tick():
        cfg = ctx.config
        if not cfg.get("enable_auto_say", False):
            return
        cids = _parse_ids(cfg.get("auto_say_chat_ids", ""))
        if not cids:
            return
        phrases_raw = str(cfg.get("auto_say_phrases", "") or "").strip()
        user_phrases = [p.strip() for p in phrases_raw.replace("\r\n", "\n").split("\n") if p.strip()]
        use_lyrics = cfg.get("auto_say_use_lyrics", True)
        if not user_phrases and not use_lyrics:
            return

        # 构建发言池
        class PoolItem:
            __slots__ = ("text", "next_text")
        pool = [PoolItem() for _ in range(len(user_phrases))]
        for i, p in enumerate(user_phrases):
            pool[i].text = p
            pool[i].next_text = None

        if use_lyrics and _LYRICS:
            for l in random.sample(list(_LYRICS), min(10, len(_LYRICS))):
                parts = None
                for sep in ("，", "。", "；", "！", "？", ",", "?"):
                    if sep in l:
                        s = l.split(sep, 1)
                        parts = (s[0].strip(), s[1].strip())
                        break
                if parts and parts[0]:
                    item = PoolItem()
                    item.text = parts[0]
                    item.next_text = parts[1] if parts[1] else None
                    pool.append(item)
                elif l:
                    item = PoolItem()
                    item.text = l
                    item.next_text = None
                    pool.append(item)
        if len(pool) < 1:
            return

        # 时间区间检查
        try:
            t_start = str(cfg.get("auto_say_time_start", "00:00") or "00:00")
            t_end = str(cfg.get("auto_say_time_end", "23:59") or "23:59")
            from datetime import datetime as _dt
            now_str = _dt.now().strftime("%H:%M")
            if t_start <= t_end:
                ok = t_start <= now_str <= t_end
            else:
                ok = now_str >= t_start or now_str <= t_end
            if not ok:
                return
        except Exception:
            pass

        now = time.time()
        next_ts = ctx.kv.get("auto_say_next_ts", None)
        if next_ts is None:
            lo = max(1, int(cfg.get("auto_say_min_minutes", 5) or 5))
            hi = int(cfg.get("auto_say_max_minutes", 8) or 8)
            if hi < lo:
                hi = lo
            ctx.kv.set("auto_say_next_ts", now + random.uniform(lo, hi) * 60)
            return
        if now < next_ts:
            return
        lo = max(1, int(cfg.get("auto_say_min_minutes", 5) or 5))
        hi = int(cfg.get("auto_say_max_minutes", 8) or 8)
        if hi < lo:
            hi = lo
        ctx.kv.set("auto_say_next_ts", now + random.uniform(lo, hi) * 60)

        apps = list(ctx.user_apps or [])
        if not apps:
            return
        client = apps[0]

        chosen = random.sample(pool, min(random.randint(1, 3), len(pool)))
        for chat_id in cids:
            msgs = []
            for item in chosen:
                msgs.append(item.text)
                if item.next_text:
                    msgs.append(item.next_text)
            for i, msg in enumerate(msgs):
                try:
                    sent = await client.send_message(chat_id, msg)
                    ctx.log.info("[AI] 自动发言 group=%s: %s", chat_id, msg[:30])
                    # 保存发言消息ID，用于检测答题奖励回复
                    pending = ctx.kv.get("auto_say_pending_rewards", [])
                    pending.append({"chat_id": chat_id, "msg_id": sent.id, "time": time.time()})
                    ctx.kv.set("auto_say_pending_rewards", pending[-20:])
                except Exception as e:  # noqa: BLE001
                    ctx.log.warning("[AI] 自动发言发送失败 group=%s: %r", chat_id, e)
                if i < len(msgs) - 1:
                    await asyncio.sleep(random.uniform(3, 8))
            await asyncio.sleep(1)

    ctx.schedule(auto_say_tick, "interval", minutes=1, id="AI自动发言")

    # ── 答题奖励（自动发言触发后，回复机器人的数学题） ──
    @ctx.on_message(ctx.filters.group & ctx.filters.text, group=6)
    async def _reward_handler(client, message):
        if not ctx.config.get("enable_auto_say", False):
            return
        if not ctx.config.get("enable_reward_answer", False):
            return
        if not message.reply_to_message_id:
            return
        # 检查是不是来自指定机器人
        reward_bots = str(ctx.config.get("reward_bot_ids", "") or "").strip()
        if reward_bots:
            bot_ids = [b.strip() for b in reward_bots.replace("，", ",").split(",") if b.strip()]
            sender_id = str(message.from_user.id) if message.from_user else ""
            sender_name = (message.from_user.username or "") if message.from_user else ""
            if bot_ids and sender_id not in bot_ids and sender_name not in bot_ids:
                return
        # 检查是不是回复了我们的自动发言
        pending = ctx.kv.get("auto_say_pending_rewards", [])
        chat_id = message.chat.id
        matched = [p for p in pending if p["chat_id"] == chat_id and p["msg_id"] == message.reply_to_message_id]
        if not matched:
            return
        # 清理过期记录（>5分钟）
        now = time.time()
        ctx.kv.set("auto_say_pending_rewards", [p for p in pending if now - p.get("time", 0) < 300])

        text = (message.text or "").strip()
        # 匹配数学题: 数字 + 运算符 + 数字 = ?
        m = re.search(r"(\d+)\s*([+\-×xX*/])\s*(\d+)\s*=\s*\?", text)
        if not m:
            return
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        if op in ("+",):
            ans = a + b
        elif op in ("-",):
            ans = a - b
        elif op in ("×", "x", "X", "*"):
            ans = a * b
        elif op in ("/",):
            ans = a // b if b != 0 else 0
        else:
            return
        ctx.log.info("[AI] 答题奖励: %d %s %d = %d", a, op, b, ans)
        await client.send_message(chat_id, str(ans), reply_to_message_id=message.id)
        # 暂停自动发言，等答题完成后再继续
        ctx.kv.set("auto_say_next_ts", time.time() + 60)
        ctx.log.info("[AI] 答题完成，60秒后继续自动发言")

    # ── .sum 群消息总结 ──────────────────────────────────────────────
    @ctx.on_message(ctx.filters.group & ctx.filters.text, group=7)
    async def _sum_handler(client, message):
        text = (message.text or "").strip()
        if not text.startswith(".sum"):
            return
        parts = text.split()
        sub = parts[1] if len(parts) > 1 else ""
        args = parts[2:] if len(parts) > 2 else []
        cfg = ctx.config
        chat_id = str(message.chat.id)

        try:
            # .sum [数量] - 快速总结
            if not sub:
                # 无参数显示帮助
                help_text = (
                    "📊 <b>群消息总结</b>\n\n"
                    "<b>快速总结</b>\n"
                    "<code>.sum 100</code> — 总结最近100条消息\n"
                    "<code>.sum 50</code> — 总结最近50条\n\n"
                    "<b>定时任务</b>\n"
                    "<code>.sum add 群组 2h 100</code> — 添加定时总结\n"
                    "<code>.sum list</code> — 查看所有任务\n"
                    "<code>.sum run 1</code> — 立即执行任务\n"
                    "<code>.sum del 1</code> — 删除任务\n\n"
                    "<b>间隔格式</b>\n"
                    "简化: <code>2h</code> (2小时), <code>30m</code> (30分钟)\n"
                    "Cron: <code>0 0 9,15,21 * * *</code>\n\n"
                    "💡 使用 AI 助手的 API Key 配置，无需额外设置"
                )
                await message.edit(help_text)
                return
            if re.match(r"^\d+$", sub):
                count = int(sub)
                await message.edit("⏳ 正在获取消息并总结...")
                result = await _sum_do(client, cfg, chat_id, count)
                if result["success"]:
                    header = f"📊 群组总结\n{result['title']} · {_sum_now()}\n\n"
                    await client.send_message(message.chat.id, header + result["result"])
                else:
                    await message.edit(f"❌ {result['error']}")
                return

            help_text = (
                "📊 <b>群消息总结</b>\n\n"
                "<b>快速总结</b>\n"
                "<code>.sum 100</code> — 总结最近100条\n\n"
                "<b>定时任务</b>\n"
                "<code>.sum add 群组 2h 100</code> — 添加定时总结\n"
                "<code>.sum list</code> — 查看任务\n"
                "<code>.sum run 1</code> — 立即执行\n"
                "<code>.sum del 1</code> — 删除任务\n\n"
                "<b>间隔格式</b>\n"
                "简化: 2h, 30m\n"
                "Cron: 0 0 9,15,21 * * *"
            )
            await message.edit(help_text)
        except Exception as e:
            await message.edit(f"❌ {e}")

    @ctx.on_api("/auto_say_test", methods=["POST"])
    async def _api_auto_say_test(req):
        try:
            # 跳过定时器检查，强制触发一次
            ctx.kv.set("auto_say_next_ts", 0)
            await auto_say_tick()
            return {"ok": True, "message": "已触发自动发言"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # ── 前端(Config.vue)用的后端接口 ──
    @ctx.on_api("/test", methods=["POST"])
    async def _api_test(req):
        cfg = ctx.config
        if not cfg.get("api_key"):
            return {"ok": False, "message": "未配置 API Key"}
        try:
            reply = await generate(
                cfg.get("api_key", ""), cfg.get("base_url", ""),
                cfg.get("model", "gpt-3.5-turbo"),
                [{"role": "user", "content": "ping"}],
            )
            return {"ok": True, "model": cfg.get("model", ""),
                    "message": "连接正常" + (f"（回复：{reply[:30]}）" if reply else "")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": classify_error(e)}

    @ctx.on_api("/histories", methods=["GET"])
    async def _api_histories(req):
        items = []
        try:
            keys = [k for k in ctx.kv.keys() if str(k).startswith("hist:")]
        except Exception:  # noqa: BLE001
            keys = []
        for k in keys:
            try:
                chat_id = int(str(k)[len("hist:"):])
            except (ValueError, TypeError):
                continue
            hist = ctx.kv.get(k, []) or []
            if not isinstance(hist, list) or not hist:
                continue
            last = ""
            for m in reversed(hist):
                if isinstance(m, dict) and m.get("content"):
                    last = str(m["content"])
                    break
            items.append({
                "chat_id": chat_id, "is_private": chat_id > 0,
                "count": len(hist), "last": last[:60],
            })
        items.sort(key=lambda x: x["count"], reverse=True)
        # 下次主动搭话时刻（epoch → 本地时间字符串）
        proactive_next = ""
        nxt = ctx.kv.get("proactive_next_ts", None)
        if nxt:
            try:
                from datetime import datetime
                proactive_next = datetime.fromtimestamp(float(nxt)).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:  # noqa: BLE001
                proactive_next = ""
        return {"items": items, "proactive_next": proactive_next}

    @ctx.on_api("/history", methods=["GET"])
    async def _api_history(req):
        raw = (req.query.get("chat_id") if hasattr(req, "query") else None) or ""
        try:
            chat_id = int(raw)
        except (ValueError, TypeError):
            return {"chat_id": raw, "messages": []}
        hist = ctx.kv.get(_hist_key(chat_id), []) or []
        msgs = [{"role": m.get("role", ""), "content": m.get("content", "")}
                for m in hist if isinstance(m, dict)]
        return {"chat_id": chat_id, "messages": msgs}

    @ctx.on_api("/history/clear", methods=["POST"])
    async def _api_history_clear(req):
        data = req.json or {}
        if data.get("all"):
            try:
                keys = [k for k in ctx.kv.keys() if str(k).startswith("hist:")]
            except Exception:  # noqa: BLE001
                keys = []
            for k in keys:
                try:
                    ctx.kv.delete(k)
                except Exception:  # noqa: BLE001
                    pass
            return {"ok": True, "cleared": len(keys)}
        chat_id = data.get("chat_id")
        if chat_id is None:
            return {"ok": False, "message": "缺少 chat_id"}
        try:
            ctx.kv.delete(_hist_key(int(chat_id)))
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True}


async def _extract_image(client, reply, ctx):
    """下载被回复消息里的图片/文档为 bytes，失败返回 None。"""
    media = getattr(reply, "photo", None) or getattr(reply, "document", None)
    if not media:
        return None
    tmp_path = None
    downloaded = None
    try:
        suffix = ".jpg"
        doc = getattr(reply, "document", None)
        if doc and getattr(doc, "file_name", None) and "." in doc.file_name:
            suffix = "." + doc.file_name.rsplit(".", 1)[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as t:
            tmp_path = t.name
        downloaded = await client.download_media(media, file_name=tmp_path)
        with open(downloaded or tmp_path, "rb") as f:
            return f.read()
    except Exception as e:  # noqa: BLE001
        ctx.log.debug("[AI] 下载图片失败: %r", e)
        return None
    finally:
        for p in (downloaded, tmp_path):
            if p and isinstance(p, str) and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


async def _auto_del(message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


async def _edit_autodel(message, text: str, delay: int = 30):
    try:
        m = await message.edit(text)
    except Exception:
        m = message
    asyncio.create_task(_auto_del(m, delay))


# ─── 群消息总结 ────────────────────────────────────────────────────────────────

import re as _re
from datetime import datetime as _dt, timezone as _tz, timedelta as _td

_SUM_TZ = _tz(_td(hours=8))

_SUM_PROMPT = (
    "你是 Telegram 群聊摘要助手。根据以下聊天记录，输出中文总结。\n"
    "每条消息末尾都有来源链接。每条摘要都必须附带来源链接。\n"
    "合并重复消息，忽略纯寒暄、表情、广告、机器人状态。\n"
    "总长度控制在 900-1600 字。\n\n"
    "固定输出：\n"
    "<b>📌 本次摘要</b>\n"
    "用 2-3 句话概括，末尾附来源链接。\n"
    "随后按实际内容选择栏目：\n"
    "<b>💬 主要话题</b>：日常交流、综合讨论\n"
    "<b>🧩 技术与项目</b>：技术方案、开发、排障\n"
    "<b>📰 资源分享</b>：外部链接、工具、新闻\n"
    "每个栏目使用 <blockquote expandable> 包裹。\n"
    "禁止使用 Markdown 语法。"
)


def _sum_now() -> str:
    return _dt.now(_SUM_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _sum_fmt_ts(ts: float) -> str:
    return _dt.fromtimestamp(ts, _SUM_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _sum_parse_interval(s: str) -> str | None:
    s = s.strip().lower()
    parts = s.split()
    if len(parts) == 6:
        return s
    if len(parts) == 5:
        return f"0 {s}"
    m = _re.match(r"^(\d+)(h|m)$", s)
    if m:
        val = int(m.group(1))
        if val <= 0:
            return None
        return f"0 0 */{val} * * *" if m.group(2) == "h" else f"0 */{val} * * * *"
    return None


def _sum_parse_chat(input_str: str) -> str:
    s = input_str.strip()
    if _re.match(r"^-?\d+$", s):
        return s
    m = _re.search(r"t\.me/c/(\d+)", s)
    if m:
        return f"-100{m.group(1)}"
    m = _re.search(r"t\.me/([a-zA-Z0-9_]+)", s)
    if m:
        return f"@{m.group(1)}"
    if s.startswith("@"):
        return s
    return s


def _sum_build_link(chat_id: str, msg_id: int, username: str = "") -> str:
    if username:
        return f"https://t.me/{username}/{msg_id}"
    cid = chat_id.replace("-100", "").replace("-", "")
    return f"https://t.me/c/{cid}/{msg_id}"


async def _sum_get_msgs(client, chat_id: str, count: int, time_range: int = 0) -> list:
    from pyrogram.raw.functions.messages import GetHistory
    peer = await client.resolve_peer(int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id)
    all_msgs = []
    offset = 0
    while len(all_msgs) < count:
        raw = await client.invoke(GetHistory(
            peer=peer, offset_id=offset, offset_date=0,
            add_offset=0, limit=min(count - len(all_msgs), 100),
            max_id=0, min_id=0, hash=0,
        ))
        msgs = [m for m in raw.messages if hasattr(m, "id") and hasattr(m, "message")]
        if not msgs:
            break
        for m in msgs:
            ts = getattr(m, "date", 0)
            if time_range and ts:
                from datetime import datetime as _dt2
                msg_time = _dt2.fromtimestamp(ts)
                if (_dt.now(_SUM_TZ) - msg_time).total_seconds() > time_range * 3600:
                    continue
            all_msgs.append({"id": m.id, "text": m.message or "", "date": ts})
            if len(all_msgs) >= count:
                break
        offset = msgs[-1].id
        if len(msgs) < 100:
            break
    return all_msgs


async def _sum_format_ai(chat_id: str, msgs: list, username: str = "") -> str:
    lines = []
    for m in msgs:
        link = _sum_build_link(chat_id, m["id"], username)
        ds = _sum_fmt_ts(m["date"]) if m.get("date") else ""
        lines.append(f"[{ds}] {m['text']}\n来源: {link}")
    return "\n---\n".join(lines)


async def _sum_do(client, cfg, chat_id: str, count: int, time_range: int = 0, prompt: str = "") -> dict:
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", "")
    model = cfg.get("model", "gpt-4o-mini")
    if not api_key:
        return {"success": False, "error": "未配置AI API Key"}

    # 获取群组信息
    try:
        peer = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
        entity = await client.get_chat(peer)
        username = getattr(entity, "username", "") or ""
        title = getattr(entity, "title", "") or chat_id
    except Exception:
        username = ""
        title = chat_id

    # 获取消息
    msgs = await _sum_get_msgs(client, chat_id, count, time_range)
    if not msgs:
        return {"success": False, "error": "未找到消息"}

    formatted = await _sum_format_ai(chat_id, msgs, username)
    final_prompt = prompt or _SUM_PROMPT

    # 调用AI
    try:
        from ._engine import generate
        result = await generate(
            api_key=api_key,
            base_url=base_url or None,
            model=model,
            messages=[{"role": "user", "content": f"{final_prompt}\n\n{formatted}"}],
        )
        # 清理思考标签
        result = _re.sub(r"<thinking>.*?</thinking>", "", result, flags=_re.DOTALL | _re.IGNORECASE)
        result = _re.sub(r" thinking.*? response", "", result, flags=_re.DOTALL | _re.IGNORECASE)
        result = result.strip()
        return {"success": True, "result": result, "title": title}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def teardown(ctx):
    _recent.clear()
