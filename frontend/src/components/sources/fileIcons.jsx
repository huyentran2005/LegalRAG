import { FileText, FileSpreadsheet, File as FileIcon } from "lucide-react";

export function FileTypeIcon({ type, ...props }) {
  if (type === "xlsx") return <FileSpreadsheet {...props} />;
  if (type === "doc") return <FileIcon {...props} />;
  return <FileText {...props} />;
}
