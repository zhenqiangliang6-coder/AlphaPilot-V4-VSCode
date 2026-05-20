-- CreateEnum
CREATE TYPE "TaskStatus" AS ENUM ('pending', 'running', 'done', 'failed');

-- CreateEnum
CREATE TYPE "StepType" AS ENUM ('analyze', 'plan', 'write', 'refine', 'test', 'fix', 'doc', 'docstring');

-- CreateEnum
CREATE TYPE "FileOpType" AS ENUM ('create', 'update', 'delete');

-- CreateEnum
CREATE TYPE "FileRole" AS ENUM ('main', 'test', 'doc', 'config', 'meta');

-- CreateEnum
CREATE TYPE "OwnerType" AS ENUM ('user', 'project', 'task', 'file', 'doc', 'memory');

-- CreateEnum
CREATE TYPE "MemoryType" AS ENUM ('preference', 'rule', 'summary', 'pattern');

-- CreateTable
CREATE TABLE "User" (
    "id" SERIAL NOT NULL,
    "external_id" TEXT,
    "name" TEXT,
    "preferences" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Project" (
    "id" SERIAL NOT NULL,
    "user_id" INTEGER,
    "name" TEXT NOT NULL,
    "root_path" TEXT,
    "repo_url" TEXT,
    "tech_stack" JSONB NOT NULL DEFAULT '{}',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Project_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Task" (
    "id" TEXT NOT NULL,
    "user_id" INTEGER,
    "project_id" INTEGER,
    "source" TEXT,
    "model" TEXT,
    "prompt" TEXT,
    "status" "TaskStatus" NOT NULL DEFAULT 'pending',
    "result_summary" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finished_at" TIMESTAMP(3),

    CONSTRAINT "Task_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TaskStep" (
    "id" SERIAL NOT NULL,
    "task_id" TEXT NOT NULL,
    "step_type" "StepType" NOT NULL,
    "status" "TaskStatus" NOT NULL DEFAULT 'pending',
    "input" JSONB,
    "output" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finished_at" TIMESTAMP(3),

    CONSTRAINT "TaskStep_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TaskFileOp" (
    "id" SERIAL NOT NULL,
    "task_id" TEXT NOT NULL,
    "step_id" INTEGER,
    "op" "FileOpType" NOT NULL,
    "path" TEXT NOT NULL,
    "role" "FileRole",
    "reason" TEXT,
    "from_step" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TaskFileOp_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "File" (
    "id" SERIAL NOT NULL,
    "project_id" INTEGER NOT NULL,
    "path" TEXT NOT NULL,
    "current_version_id" INTEGER,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "File_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FileVersion" (
    "id" SERIAL NOT NULL,
    "file_id" INTEGER NOT NULL,
    "task_id" TEXT,
    "step_id" INTEGER,
    "content" TEXT NOT NULL,
    "hash" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "FileVersion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Memory" (
    "id" SERIAL NOT NULL,
    "owner_type" "OwnerType" NOT NULL,
    "user_id" INTEGER,
    "project_id" INTEGER,
    "task_id" TEXT,
    "file_id" INTEGER,
    "memory_type" "MemoryType" NOT NULL,
    "content" TEXT NOT NULL,
    "importance" INTEGER NOT NULL DEFAULT 1,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Memory_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_external_id_key" ON "User"("external_id");

-- AddForeignKey
ALTER TABLE "Project" ADD CONSTRAINT "Project_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Task" ADD CONSTRAINT "Task_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Task" ADD CONSTRAINT "Task_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TaskStep" ADD CONSTRAINT "TaskStep_task_id_fkey" FOREIGN KEY ("task_id") REFERENCES "Task"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TaskFileOp" ADD CONSTRAINT "TaskFileOp_task_id_fkey" FOREIGN KEY ("task_id") REFERENCES "Task"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TaskFileOp" ADD CONSTRAINT "TaskFileOp_step_id_fkey" FOREIGN KEY ("step_id") REFERENCES "TaskStep"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "File" ADD CONSTRAINT "File_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FileVersion" ADD CONSTRAINT "FileVersion_file_id_fkey" FOREIGN KEY ("file_id") REFERENCES "File"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FileVersion" ADD CONSTRAINT "FileVersion_task_id_fkey" FOREIGN KEY ("task_id") REFERENCES "Task"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FileVersion" ADD CONSTRAINT "FileVersion_step_id_fkey" FOREIGN KEY ("step_id") REFERENCES "TaskStep"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Memory" ADD CONSTRAINT "Memory_user_fk" FOREIGN KEY ("user_id") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Memory" ADD CONSTRAINT "Memory_project_fk" FOREIGN KEY ("project_id") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Memory" ADD CONSTRAINT "Memory_task_fk" FOREIGN KEY ("task_id") REFERENCES "Task"("id") ON DELETE CASCADE ON UPDATE CASCADE;
