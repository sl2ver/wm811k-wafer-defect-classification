"""Check that torch sees the GPU and time a tiny CNN on GPU vs CPU (no seed; timing only).

Usage (from project root):
    .venv\\Scripts\\python scripts\\check_gpu.py
"""
import time, torch
print("torch", torch.__version__, "| cuda build", torch.version.cuda, "| cudnn", torch.backends.cudnn.version())
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0), "| capability", torch.cuda.get_device_capability(0))
    print("arch list:", torch.cuda.get_arch_list())
net = torch.nn.Sequential(torch.nn.Conv2d(1, 32, 3, padding=1), torch.nn.ReLU(), torch.nn.Conv2d(32, 64, 3, padding=1), torch.nn.ReLU(),
                          torch.nn.AdaptiveAvgPool2d(1), torch.nn.Flatten(), torch.nn.Linear(64, 9))
x = torch.randn(256, 1, 64, 64); y = torch.randint(0, 9, (256,))
for dev in (["cuda"] if torch.cuda.is_available() else []) + ["cpu"]:
    m = net.to(dev); xb, yb = x.to(dev), y.to(dev); opt = torch.optim.SGD(m.parameters(), lr=0.01)
    for i in range(3):  # warm-up
        opt.zero_grad(); torch.nn.functional.cross_entropy(m(xb), yb).backward(); opt.step()
    if dev == "cuda": torch.cuda.synchronize()
    t0 = time.perf_counter()
    for i in range(20):
        opt.zero_grad(); loss = torch.nn.functional.cross_entropy(m(xb), yb); loss.backward(); opt.step()
    if dev == "cuda": torch.cuda.synchronize()
    print(f"{dev}: 20 fwd+bwd steps (batch 256, 1x64x64) {time.perf_counter()-t0:.3f} s, loss {loss.item():.4f}")
