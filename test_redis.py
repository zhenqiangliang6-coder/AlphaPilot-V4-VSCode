from upstash_redis import Redis

# 用你在 Upstash 控制台拿到的 URL 和 TOKEN
redis = Redis(
    url="https://growing-cub-282898.upstash.io",
    token="gQAAAAAABFESAAIgcDEwNzcxOTMwZGI1NGM0NDYwYTYwMzNhMjYzYjg3NzY3ZA"
)

# 测试连接
print(redis.ping())  # 应该返回 "PONG"
