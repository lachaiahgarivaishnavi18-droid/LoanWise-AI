"""Record the installed core dependency closure without pulling optional Torch into Docker."""
from pathlib import Path
import importlib.metadata as metadata
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT=Path(__file__).resolve().parents[1]
pending=[Requirement(line) for line in (ROOT/'backend/requirements.txt').read_text().splitlines() if line.strip() and not line.startswith('#')]
visited={}
versions={}
while pending:
    requirement=pending.pop()
    name=canonicalize_name(requirement.name)
    extras=set(requirement.extras)|{''}
    if name in visited and extras.issubset(visited[name]):
        continue
    visited.setdefault(name,set()).update(extras)
    dist=metadata.distribution(name)
    versions[name]=dist.version
    for raw in dist.requires or []:
        child=Requirement(raw)
        if child.marker is None or any(child.marker.evaluate({'extra':extra}) for extra in visited[name]):
            pending.append(child)
lines=['# Tested core version constraints. Optional neural/GPU packages are deliberately excluded.']
lines.extend(f'{name}=={version}' for name,version in sorted(versions.items()))
(ROOT/'backend/requirements-lock.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f'Recorded {len(versions)} installed core package versions.')
