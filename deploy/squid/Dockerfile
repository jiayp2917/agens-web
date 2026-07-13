FROM alpine:3.22

RUN apk add --no-cache squid

COPY entrypoint.sh /usr/local/bin/agens-squid-entrypoint
RUN chmod 0555 /usr/local/bin/agens-squid-entrypoint

USER squid

EXPOSE 3128

ENTRYPOINT ["/usr/local/bin/agens-squid-entrypoint"]
