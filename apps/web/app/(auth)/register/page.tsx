"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { register } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import {
  type RegisterInput,
  registerSchema,
} from "@/lib/validation/schemas";

const inputClass =
  "w-full rounded-lg border border-black/15 px-3 py-2.5 text-[15px] outline-none focus:border-black/40";

export default function RegisterPage() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register: registerField,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterInput>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: "", password: "", confirmPassword: "", nickname: "" },
    mode: "onBlur",
  });

  async function onSubmit(values: RegisterInput) {
    setServerError(null);
    try {
      await register({
        email: values.email,
        password: values.password,
        nickname: values.nickname || undefined,
      });
      router.push("/onboarding/goals");
    } catch (err) {
      if (err instanceof ApiError && err.code === "email_taken") {
        setError("email", { message: "该邮箱已被注册" });
        return;
      }
      setServerError(err instanceof ApiError ? err.message : "注册失败，请稍后重试");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[420px] flex-col justify-center px-6 py-12">
      <h1 className="text-[26px] font-medium tracking-tight">创建账号</h1>
      <p className="mt-1.5 text-[14px] text-black/50">
        记录饮食，先从设定目标开始
      </p>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-8 space-y-4" noValidate>
        <div>
          <input
            type="email"
            autoComplete="email"
            placeholder="邮箱"
            {...registerField("email")}
            className={inputClass}
          />
          {errors.email && <Err msg={errors.email.message} />}
        </div>

        <div>
          <input
            type="password"
            autoComplete="new-password"
            placeholder="密码（至少 8 位，含字母和数字）"
            {...registerField("password")}
            className={inputClass}
          />
          {errors.password && <Err msg={errors.password.message} />}
        </div>

        <div>
          <input
            type="password"
            autoComplete="new-password"
            placeholder="确认密码"
            {...registerField("confirmPassword")}
            className={inputClass}
          />
          {errors.confirmPassword && <Err msg={errors.confirmPassword.message} />}
        </div>

        <div>
          <input
            type="text"
            placeholder="昵称（选填）"
            {...registerField("nickname")}
            className={inputClass}
          />
          {errors.nickname && <Err msg={errors.nickname.message} />}
        </div>

        {serverError && (
          <p className="rounded-lg bg-red-50 px-3 py-2.5 text-[14px] text-red-700">
            {serverError}
          </p>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-lg bg-black px-4 py-3 text-[15px] font-medium text-white disabled:opacity-40"
        >
          {isSubmitting ? "创建中…" : "注册"}
        </button>
      </form>

      <p className="mt-6 text-center text-[14px] text-black/50">
        已有账号？{" "}
        <Link href="/login" className="font-medium text-black underline">
          去登录
        </Link>
      </p>
    </main>
  );
}

function Err({ msg }: { msg?: string }) {
  if (!msg) return null;
  return <p className="mt-1 text-[13px] text-red-600">{msg}</p>;
}
