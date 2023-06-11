
# Research list:
# Extraction:
# * Named Entity Recognition (NER)
# Aggregation:
# * To represent an entire paragraph as one vector, several methods:
# * * averaging, max pooling, CLS / BERT
# For locally running the models we might be just able to:
# * Hugging Face Transformers Python library (pip install transformers)
# * Facebook Faiss (vector DB)
# * Pinecone, a fully managed vector database
# * Weaviate, an open-source vector search engine
# * Redis as a vector database
# * Qdrant, a vector search engine
# * Milvus, a vector database built for scalable similarity search
# * Chroma, an open-source embeddings store
# * Typesense, fast open source vector search
# * Zilliz, data infrastructure, powered by Milvus
# * https://github.com/pgvector/pgvector: SELECT * FROM items ORDER BY embedding <-> '[3,1,2]' LIMIT 5;