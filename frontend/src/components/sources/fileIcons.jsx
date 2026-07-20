import { FileText, FileSpreadsheet, File as FileIcon } from "lucide-react";

export function fileIconFor(type) {
  if (type === "xlsx") return FileSpreadsheet;
  if (type === "doc") return FileIcon;
  return FileText;
}

export function FileTypeIcon({ type, ...props }) {
  if (type === "xlsx") return <FileSpreadsheet {...props} />;
  if (type === "doc") return <FileIcon {...props} />;
  return <FileText {...props} />;
}
