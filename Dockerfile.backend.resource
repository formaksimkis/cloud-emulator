FROM nginx:alpine

# Copy static resources
COPY backend-resource /usr/share/nginx/html/resource
