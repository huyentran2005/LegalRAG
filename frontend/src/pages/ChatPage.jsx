import { RagProvider } from "../context/RagContext";
import Header from "../components/layout/Header";
import SourcesSidebar from "../components/sources/SourcesSideBar";
import ChatThread from "../components/chat/ChatThread";
import Composer from "../components/chat/Composer";
import CitationPanel from "../components/citation/CitationPanel";

export default function ChatPage() {
  return (
    <RagProvider>
      <div className="h-screen w-full flex flex-col overflow-hidden bg-paper text-ink font-sans">
        <Header />
        <div className="flex-1 flex min-h-0">
          <SourcesSidebar />
          <main className="flex-1 flex flex-col min-w-0">
            <ChatThread />
            <Composer />
          </main>
          <CitationPanel />
        </div>
      </div>
    </RagProvider>
  );
}
