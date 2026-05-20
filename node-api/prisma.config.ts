import "dotenv/config";
import { defineConfig } from "prisma/config";

export default defineConfig({
  schema: "./prisma/schema.prisma",
  migrations: {
    path: "./prisma/migrations",
  },
  datasource: {
    provider: "postgresql",
    url: process.env.DATABASE_URL,
  },
  client: {
    provider: "prisma-client-js",
  },
  // Prisma 7.x 使用 engineType 配置
  engineType: "library",
});