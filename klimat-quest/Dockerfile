FROM python:3.12-slim
WORKDIR /app
COPY server.py index.html questions.txt ./
RUN sed -i 's/chosen.extend(sample)/chosen.extend([dict(topic=q["topic"],question=q["question"],options=q["options"][:]) for q in sample])/' server.py
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8000
EXPOSE 8000
CMD ["python","server.py"]
