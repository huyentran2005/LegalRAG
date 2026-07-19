export const SOURCES = [
  { id: "s1", name: "Cẩm nang nhân viên.pdf", meta: "24 trang", type: "pdf", checked: true },
  { id: "s2", name: "Báo cáo Q3 2026.xlsx", meta: "12 trang", type: "xlsx", checked: true },
  { id: "s3", name: "Ghi chú họp chiến lược.docx", meta: "6 trang", type: "doc", checked: true },
  { id: "s4", name: "Chính sách bảo mật.pdf", meta: "18 trang", type: "pdf", checked: false },
];

export const CITATIONS = {
  1: {
    sourceId: "s2",
    sourceName: "Báo cáo Q3 2026.xlsx",
    page: "Trang 4",
    excerpt:
      "Doanh thu quý 3 đạt 42,3 tỷ đồng, tăng 18% so với quý liền trước, đánh dấu quý tăng trưởng mạnh nhất trong năm.",
  },
  2: {
    sourceId: "s2",
    sourceName: "Báo cáo Q3 2026.xlsx",
    page: "Trang 7",
    excerpt:
      "Mảng dịch vụ doanh nghiệp đóng góp 61% tổng doanh thu quý này, dẫn đầu bởi các hợp đồng gia hạn dài hạn.",
  },
  3: {
    sourceId: "s1",
    sourceName: "Cẩm nang nhân viên.pdf",
    page: "Trang 15",
    excerpt:
      "Các khoản ngân sách vượt 500 triệu đồng cần được phê duyệt bởi Giám đốc Tài chính. Vượt 1 tỷ đồng cần thêm xác nhận từ Ban điều hành.",
  },
};

export const INITIAL_MESSAGES = [
  { id: "m1", role: "user", text: "Doanh thu quý 3 tăng bao nhiêu so với quý 2?" },
  {
    id: "m2",
    role: "assistant",
    parts: [
      { text: "Theo báo cáo tài chính, doanh thu quý 3/2026 đạt 42,3 tỷ đồng, tăng 18% so với quý 2" },
      { cite: 1 },
      { text: ". Mức tăng này chủ yếu đến từ mảng dịch vụ doanh nghiệp, đóng góp 61% tổng doanh thu" },
      { cite: 2 },
      { text: "." },
    ],
    usedSources: ["s2"],
  },
  { id: "m3", role: "user", text: "Ai chịu trách nhiệm phê duyệt ngân sách vượt 500 triệu?" },
  {
    id: "m4",
    role: "assistant",
    parts: [
      { text: "Theo cẩm nang nhân viên, các khoản vượt 500 triệu đồng cần được Giám đốc Tài chính phê duyệt, và cần thêm xác nhận từ Ban điều hành nếu vượt 1 tỷ đồng" },
      { cite: 3 },
      { text: "." },
    ],
    usedSources: ["s1"],
  },
];
