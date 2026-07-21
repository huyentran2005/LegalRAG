from langchain_text_splitters import RecursiveCharacterTextSplitter

class TextSplitter:
    def __init__(self, chunk_size: int = 400, chunk_overlap: int = 120):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size = chunk_size,
            chunk_overlap = chunk_overlap,
            length_function = len
        )

    def split(self, documents):
        return self.splitter.split_documents(documents)
