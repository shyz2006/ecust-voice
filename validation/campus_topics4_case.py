"""Semantic and false-positive checks using independently worded synthetic campus posts."""
import runpy,pathlib,json
root=pathlib.Path('/app') if pathlib.Path('/app/CampusPulse/taxonomy.py').exists() else pathlib.Path(__file__).resolve().parent.parent/'production'
classify=runpy.run_path(str(root/'CampusPulse/taxonomy.py'))['classify']
cases={
 '学业课程':['选修课要算在哪个学分板块？','这门创业基础是不是必修？','形势与政策能补选吗','课程设计什么时候交','想了解辅修申请流程','制药工程小设计求讨论','毕设导师怎么选啊[大哭][大哭]'],
 '考试考证':['编程模拟考安排在哪天','六级考试能改报名吗[大哭][大哭]','明天闭卷小测范围是什么'],
 '校园设施与管理':['教学楼有没有安静的空间','过闸机校园牌没声音','马路中间刷手机真的挡路','公共场合大声喧哗影响别人','学校的信息门户无法打开'],
 '宿舍生活':['舍敌天天吵，没法休息','寝友总在半夜说话','浴室十一点没水了[大哭][大哭]'],
 '社交与同伴':['突然被单删了，一头雾水','谢谢那个帮我撑伞的同学','想找一个羽毛球搭子','你们都在哪个老乡群','能不能让我遇到正常人'],
 '恋爱情感':['想谈恋爱但不知道怎么表白','异地恋分手后还想复合'],
 '身心与情绪':['啊啊啊啊啊啊[大哭][大哭]','最近情绪低落，想倾诉','牙疼想去校医院'],
 '文体与实践':['华体内控没有点位怎么办','新生晚会的照片拍得很棒','想加入棋艺社怎么联系','求钢琴社联系方式','有人玩星际猎人吗','体测时间什么时候'],
 '食堂与生活服务':['平时早上吃什么','学校附近可以卸甲吗','耳夹式耳机有推荐吗','哪里可以打耳骨钉','衣服穿不下大家怎么处理'],
 '交易与互助':['收两公斤哑铃，带价来','出三文鱼400g，120r','出一盒苹果可刀','双十一有人拼鱼油吗','30块一箱纸巾，有需者来','有人看到一个水杯吗','有同学能出我一把雨伞吗，价格好说','借b站大会员抽名额','收一本考研书，带价来','有没有人能代拿快递，有偿'],
 '其他校园讨论':['接上一条','[白眼]','明天下午！！！','win or lose','出太阳了','收获满满','你出来一下','这个是真的吗'],
}
fail=[];total=0
for theme,texts in cases.items():
 for text in texts:
  total+=1;actual=classify(text)
  if actual['theme']!=theme:fail.append({'text':text,'expected':theme,'actual':actual})
result={'passed':not fail,'cases':total,'failures':fail,'version':'campus-topics-4','model_calls':0}
print(json.dumps(result,ensure_ascii=False));assert not fail
