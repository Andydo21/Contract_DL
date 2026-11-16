# The chaincode, compiled once into the image (it used to be compiled by `go run` at every start).
# After changing a .go file:  docker compose build fabric-chaincode && docker compose up -d fabric-chaincode
FROM golang:1.20-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY *.go ./
RUN CGO_ENABLED=0 go build -o /contract-verify .

FROM alpine:latest
COPY --from=build /contract-verify /usr/local/bin/contract-verify
COPY start.sh /start.sh
ENTRYPOINT ["/bin/sh", "/start.sh"]
