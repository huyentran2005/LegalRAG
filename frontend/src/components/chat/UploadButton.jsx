import { Link, Plus, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { uploadSource } from "../../api/client";
import { useRag } from "../../context/useRag";

export default function UploadButton(){
    const {setSources, normalizeSource, ensureSession, loadSessions} = useRag();
    const fileInputRef = useRef(null);
    const [open, setOpen] = useState(false);
    const [linkMode, setLinkMode] = useState(false);
    const [url, setUrl] = useState("");
    const [uploading, setUploading] = useState(false);

    const openFilePicker = () => {
        setOpen(false);
        fileInputRef.current.click();
    };

    const appendSource = (data) => {
        const nextSources = [data, ...(data.linkedSources || [])].map(normalizeSource);
        setSources((prev)=> [...prev, ...nextSources]);
        loadSessions();
    };
    
    const handleUpload = async(e)=>{
        const file = e.target.files[0];
        if(!file) return ;
        setUploading(true);
        try{
            const sessionId = await ensureSession();
            const data = await uploadSource({file, sessionId});
            console.log("Upload thành công:", data);
            appendSource(data);
        } catch(err){
            console.error("Upload thất bại:", err);
        } finally {
            setUploading(false);
            e.target.value = "";
        }
    }

    const handleLinkUpload = async () => {
        const trimmed = url.trim();
        if (!trimmed) return;
        setUploading(true);
        try {
            const sessionId = await ensureSession();
            const data = await uploadSource({url: trimmed, sessionId});
            appendSource(data);
            setUrl("");
            setLinkMode(false);
            setOpen(false);
        } catch (err) {
            console.error("Upload link thất bại:", err);
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="relative">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                disabled={uploading}
                className="flex items-center gap-1 text-xs font-medium text-indigo px-1.5 py-1 hover:opacity-80"
            >
                <Plus size={14} /> Thêm
            </button>
            {open && (
                <div className="absolute right-0 top-full mt-1 w-60 rounded-lg border border-line bg-white shadow-lg p-2 z-20">
                    {!linkMode ? (
                        <div className="flex flex-col">
                            <button
                                type="button"
                                onClick={openFilePicker}
                                className="flex items-center gap-2 px-2 py-2 text-sm text-ink hover:bg-panel rounded-md"
                            >
                                <Upload size={15} className="text-inkfaint" />
                                Từ máy
                            </button>
                            <button
                                type="button"
                                onClick={() => setLinkMode(true)}
                                className="flex items-center gap-2 px-2 py-2 text-sm text-ink hover:bg-panel rounded-md"
                            >
                                <Link size={15} className="text-inkfaint" />
                                Từ link
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            <input
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                placeholder="https://..."
                                className="w-full border border-line rounded-md px-2 py-1.5 text-xs outline-none focus:border-indigo"
                            />
                            <div className="flex justify-end gap-2">
                                <button
                                    type="button"
                                    onClick={() => setLinkMode(false)}
                                    className="px-2 py-1 text-xs text-inksoft hover:text-ink"
                                >
                                    Hủy
                                </button>
                                <button
                                    type="button"
                                    onClick={handleLinkUpload}
                                    disabled={uploading || !url.trim()}
                                    className="px-2 py-1 text-xs rounded-md bg-indigo text-white disabled:bg-panel disabled:text-inkfaint"
                                >
                                    Thêm
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}
            <input
                ref = {fileInputRef}
                type="file"
                accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx"
                className="hidden"
                onChange={handleUpload}
            />
        </div>
    );
}
