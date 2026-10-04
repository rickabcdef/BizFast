export default defineAppConfig({
  // 页面按模块 M1–M11 注册；首屏 m1_home 为首页
  pages: [
    'pages/m1_home/index',
    'pages/m2_diagnose/index',
    'pages/m3_match/index',
    'pages/m4_delivery/index',
    'pages/m5_pay/index',
    'pages/m6_tools/index',
    'pages/m7_games/index',
    'pages/m8_share/index',
    'pages/m9_notify/index',
    'pages/m10_user/index',
    'pages/m11_admin/index'
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#0B1026',
    navigationBarTitleText: '生意快启',
    navigationBarTextStyle: 'white',
    backgroundColor: '#0B1026'
  }
  // 科技风设计令牌见 theme/tokens.ts 与 app.scss（CSS 变量 --bf-*）
})
