import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="h-screen w-full flex flex-col items-center justify-center bg-paper text-ink font-sans gap-3">
      <span className="font-display text-2xl font-semibold">Không tìm thấy trang</span>
      <p className="text-sm text-inksoft">Trang bạn tìm không tồn tại hoặc đã được di chuyển.</p>
      <Link to="/" className="text-sm text-indigo hover:underline">
        Về trang trò chuyện
      </Link>
    </div>
  );
}
