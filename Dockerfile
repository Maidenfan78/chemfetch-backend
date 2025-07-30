FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev && npm install --omit=dev tsx
COPY server ./server
EXPOSE 3000
CMD ["npx","tsx","server/index.ts"]
