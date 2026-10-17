import type en from './en'

const vi: typeof en = {
  app: { name: 'Học tiếng Trung' },
  nav: {
    home: 'Trang chủ',
    lookup: 'Tra từ',
    flashcards: 'Thẻ từ',
    lessons: 'Bài học',
    games: 'Trò chơi',
    progress: 'Tiến độ',
    main: 'Điều hướng chính',
  },
  prefs: {
    level: 'Trình độ',
    levelHint: 'Chọn trình độ mục tiêu. Nội dung và gợi ý sẽ theo trình độ này.',
    language: 'Ngôn ngữ',
    theme: 'Giao diện',
    themes: { system: 'Theo hệ thống', light: 'Sáng', dark: 'Tối' },
    savedLocally: 'Đã lưu trên thiết bị này. Đăng nhập để dùng trên mọi thiết bị.',
  },
  home: {
    title: 'Chữ phồn thể, chú âm và pinyin',
    subtitle: 'Từ vựng, thẻ từ và luyện thi TOCFL từ A1 đến C2.',
    sample: 'Ví dụ',
    annotation: 'Phiên âm',
    none: 'Không',
  },
  account: {
    signedInAs: 'Đã đăng nhập: {name}',
    devSignIn: 'Đăng nhập tài khoản thử (dev)',
    signOut: 'Đăng xuất',
  },
  comingSoon: 'Sắp ra mắt.',
  errors: {
    network_error: 'Không kết nối được máy chủ.',
    generic: 'Đã có lỗi. Vui lòng thử lại.',
  },
}

export default vi
