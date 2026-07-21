import glob
from typing import List
from tqdm import tqdm
from langchain_community.document_loaders import PyPDFLoader
from rag.service.text import clean_vietnamese_text

class Loader:
    def load_pdf(self, pdf_file: str):
        docs = PyPDFLoader(pdf_file).load()
        for doc in docs:
            doc.page_content = clean_vietnamese_text(doc.page_content)
        return docs

    def load_dir(self, dir_path: str) -> List:
        pdf_files = glob.glob(f'{dir_path}/*.pdf')
        if not pdf_files:
            raise ValueError(f'No PDF files found in {dir_path}')
        all_docs = []

        for pdf_file in tqdm(pdf_files, desc="Loading PDF files"):
            try:
                all_docs.extend(self.load_pdf(pdf_file))
            except Exception:
                pass
        return all_docs