# Two images from one file:
# - development: the Vite development server, for the Compose development stack (compose.yaml).
# - production, the default: the built app, served by nginx, which also passes /api/ and /health/
#   to the API so the browser only talks to one origin (compose.prod.yaml).

FROM node:22-alpine AS development

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


FROM development AS build

# "/" makes the app call the API on its own origin, through nginx. A value set in the build's
# environment takes precedence over any .env file.
ARG VITE_API_BASE_URL=/
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build


# nginx without root rights, listening on 8080.
FROM nginxinc/nginx-unprivileged:1.30-alpine AS production

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/nginx-health"]
