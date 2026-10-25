"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { fetchMe, login } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import { type LoginInput, loginSchema } from "@/lib/validation/schemas";

const inputClass =
  "w-full rounded-lg border border-black/15 px-3 py-2.5 text-[15px] outline-none focus:border-black/40";

export default function LoginPage() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register: registerField,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
    mode: "onBlur",
  });

  async function onSubmit(values: LoginInput) {
    setServerError(null);
    try {
      await login(values);
      // 有目标去今日页，没目标先引导设置
      const me = await fetchMe();
      router.push(me.has_goal ? "/today" : "/onboarding/goals");
    } catch (err) {
      if (err instanceof ApiError && err.code === "invalid_credentials") {
        setServerError("邮箱或密码错误");
        return;
      }
      setServerError(err instanceof ApiError ? err.message : "登录失败，请稍后重试");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[420px] flex-col justify-center px-6 py-12">
      <h1 className="text-[26px] font-medium tracking-tight">登录</h1>
      <p className="mt-1.5 text-[14px] text-black/50">欢迎回来</p>

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
            autoComplete="current-password"
            placeholder="密码"
            {...registerField("password")}
            className={inputClass}
          />
          {errors.password && <Err msg={errors.password.message} />}
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
          {isSubmitting ? "登录中…" : "登录"}
        </button>
      </form>

      <p className="mt-6 text-center text-[14px] text-black/50">
        还没有账号？{" "}
        <Link href="/register" className="font-medium text-black underline">
          去注册
        </Link>
      </p>
    </main>
  );
}

function Err({ msg }: { msg?: string }) {
  if (!msg) return null;
  return <p className="mt-1 text-[13px] text-red-600">{msg}</p>;
}
