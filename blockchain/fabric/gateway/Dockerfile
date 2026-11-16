# The Fabric gateway with its libraries installed in the image (they used to be installed by `npm ci` at every start).
# server.js is mounted over the image's copy, so a change to it needs only a restart; a change to package.json needs
#   docker compose build fabric-gateway
FROM node:18-alpine
WORKDIR /opt/gateway
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY server.js ./
CMD ["node", "server.js"]
