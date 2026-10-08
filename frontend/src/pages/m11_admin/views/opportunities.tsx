import { useCallback, useEffect, useState } from 'react'
import { View, Text, Textarea, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import {
  getAdminOpportunities,
  getAdminOpportunityVersions,
  importOpportunities,
  reviewOpportunity,
  rollbackOpportunity,
  type AdminOpportunity
} from '@/services/bApi'

// M11-03 商机库管理（P0）：商机模板 / 行业数据 / 案例库，支持批量导入与审核
const STATUS_FILTERS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待审核' },
  { value: 'passed', label: '已通过' },
  { value: 'rejected', label: '已驳回' }
]

const IMPORT_TEMPLATE = [
  '商机名称,分类,适用城市,资金下限(元),资金上限(元),回本周期(月),毛利率(%),难度(1-5星),来源',
  '夜市柠檬茶摊,餐饮小吃,长沙,8000,15000,2,62,1,批量导入',
  '上门宠物洗护,本地生活,上海,30000,80000,6,45,3,批量导入'
].join('\n')

/** 解析粘贴的 CSV（表头按模板顺序），后端入库待审。 */
function parseCsv(text: string): AdminOpportunity[] {
  const lines = text
    .trim()
    .split(/\r?\n/)
    .filter((l) => l.trim())
  if (lines.length < 2) return []
  const headers = lines[0].split(',').map((h) => h.trim())
  const idx = (name: string) => headers.indexOf(name)
  const out: AdminOpportunity[] = []
  for (let i = 1; i < lines.length; i++) {
    const cells = lines[i].split(',').map((c) => c.trim())
    const title = cells[idx('商机名称')]
    if (!title) continue
    out.push({
      id: `OP-IMP-${Date.now()}-${i}`,
      title,
      category: cells[idx('分类')] || '未分类',
      city: cells[idx('适用城市')] || '全国',
      capitalMin: Number(cells[idx('资金下限(元)')]) || 0,
      capitalMax: Number(cells[idx('资金上限(元)')]) || 0,
      paybackMonths: Number(cells[idx('回本周期(月)')]) || 0,
      marginPercent: Number(cells[idx('毛利率(%)')]) || 0,
      difficultyStars: Number(cells[idx('难度(1-5星)')]) || 1,
      source: cells[idx('来源')] || '批量导入',
      status: 'pending',
      statusLabel: '待审核',
      createdAt: new Date().toISOString().slice(0, 10)
    })
  }
  return out
}

export default function OpportunitiesView() {
  const [rows, setRows] = useState<AdminOpportunity[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  // 批量导入
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [importBusy, setImportBusy] = useState(false)
  const [importResult, setImportResult] = useState('')
  // V5.0 M4-04 版本历史 / 回滚（保存时自动备份上一版本，所见即所得）
  const [versionOpen, setVersionOpen] = useState(false)
  const [versionItem, setVersionItem] = useState<AdminOpportunity | null>(null)
  const [versions, setVersions] = useState<{ version: number; title: string; updatedAt: string }[]>([])
  const [versionBusy, setVersionBusy] = useState(false)

  const load = useCallback(
    async (p = page, kw = keyword, st = status) => {
      setLoading(true)
      setError('')
      try {
        const d = await getAdminOpportunities({ page: p, pageSize, keyword: kw, status: st })
        setRows(d.items)
        setTotal(d.total)
      } catch (e: any) {
        setError(e?.message || '商机列表加载失败，请重试')
      } finally {
        setLoading(false)
      }
    },
    [page, keyword, status, pageSize]
  )

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  const doSearch = () => {
    setPage(1)
    void load(1, keyword, status)
  }

  const doImport = async () => {
    const items = parseCsv(importText)
    if (items.length === 0) {
      Taro.showToast({ title: '请粘贴至少 2 行：表头 + 数据', icon: 'none' })
      return
    }
    setImportBusy(true)
    setImportResult('')
    try {
      const r = await importOpportunities(items)
      setImportResult(`导入 ${r.imported} 条成功，驳回 ${r.rejected} 条。新商机进入「待审核」队列。`)
      setImportOpen(false)
      setImportText('')
      Taro.showToast({ title: `已导入 ${r.imported} 条`, icon: 'success' })
      void load(1, '', 'pending')
      setPage(1)
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '导入失败，请重试', icon: 'none' })
    } finally {
      setImportBusy(false)
    }
  }

  const doReview = async (item: AdminOpportunity, action: 'approve' | 'reject') => {
    try {
      const r = await reviewOpportunity(item.id, action)
      Taro.showToast({ title: r.message, icon: 'none' })
      void load()
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '审核操作失败，请重试', icon: 'none' })
    }
  }

  // V5.0 M4-04：打开版本历史（保存时自动备份上一版本）
  const doOpenVersions = async (item: AdminOpportunity) => {
    setVersionItem(item)
    setVersionOpen(true)
    try {
      const d = await getAdminOpportunityVersions(item.id)
      setVersions(d.versions)
    } catch (e: any) {
      setVersions([])
      Taro.showToast({ title: e?.message || '版本历史加载失败', icon: 'none' })
    }
  }

  // V5.0 M4-04：一键回滚（回到历史版本，修改后 5 分钟内对用户端生效）
  const doRollback = async (ver: number) => {
    if (!versionItem || versionBusy) return
    setVersionBusy(true)
    try {
      const r = await rollbackOpportunity(versionItem.id, ver)
      Taro.showToast({ title: r.message, icon: 'none' })
      setVersionOpen(false)
      void load()
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '回滚失败，请重试', icon: 'none' })
    } finally {
      setVersionBusy(false)
    }
  }

  return (
    <View className='m11-opps'>
      <View className='bf-card'>
        <View className='bf-row'>
          <Input
            className='bf-input m11-filter__input'
            placeholder='搜索商机名称 / 分类 / 城市'
            value={keyword}
            onInput={(e) => setKeyword(e.detail.value)}
            onConfirm={doSearch}
          />
          <View className='bf-btn bf-btn--sm' onClick={doSearch}>
            搜索
          </View>
        </View>
        <View className='m11-filter__segs'>
          {STATUS_FILTERS.map((f) => (
            <View
              key={f.value}
              className={`m11-seg ${status === f.value ? 'is-active' : ''}`}
              onClick={() => {
                setStatus(f.value)
                setPage(1)
                void load(1, keyword, f.value)
              }}
            >
              {f.label}
            </View>
          ))}
        </View>
        <View className='bf-row m11-filter__foot'>
          <Text className='bf-muted'>共 {total} 条商机</Text>
          <View className='bf-btn bf-btn--sm' onClick={() => setImportOpen(true)}>
            + 批量导入
          </View>
        </View>
      </View>

      {importResult && <Text className='m11-tip m11-tip--ok'>{importResult}</Text>}
      {loading && <Loading text='正在加载商机库…' />}
      {error && <ErrorTip message={error} onRetry={() => void load()} />}

      {!loading && !error && (
        <View className='bf-card'>
          {rows.map((o) => (
            <View key={o.id} className='m11-row'>
              <View className='m11-row__main'>
                <Text className='m11-row__title'>{o.title}</Text>
                <Text className='bf-muted m11-row__sub'>
                  {o.category} · {o.city} · 资金 {o.capitalMin / 10000}–{o.capitalMax / 10000} 万 · 回本 {o.paybackMonths} 月 · 毛利 {o.marginPercent}% · 难度 {'★'.repeat(Math.max(1, o.difficultyStars))}
                </Text>
                <Text className='bf-muted m11-row__sub'>来源：{o.source} · {o.createdAt}</Text>
              </View>
              <View className='m11-row__right'>
                <Text
                  className={`bf-tag ${o.status === 'passed' ? 'bf-tag--good' : o.status === 'rejected' ? 'bf-tag--warn' : ''}`}
                >
                  {o.statusLabel}
                </Text>
                {o.status === 'pending' && (
                  <View className='m11-row__acts'>
                    <View className='bf-btn bf-btn--sm' onClick={() => doReview(o, 'approve')}>
                      通过
                    </View>
                    <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => doReview(o, 'reject')}>
                      驳回
                    </View>
                  </View>
                )}
                <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => doOpenVersions(o)}>
                  版本
                </View>
              </View>
            </View>
          ))}
          {rows.length === 0 && <Text className='bf-muted m11-empty-line'>商机库为空</Text>}
        </View>
      )}

      {total > pageSize && (
        <View className='bf-row m11-pager'>
          <View
            className={`bf-btn bf-btn--sm bf-btn--ghost ${page <= 1 ? 'bf-btn--disabled' : ''}`}
            onClick={() => page > 1 && setPage(page - 1)}
          >
            上一页
          </View>
          <Text className='bf-muted'>{page} / {Math.max(1, Math.ceil(total / pageSize))}</Text>
          <View
            className={`bf-btn bf-btn--sm bf-btn--ghost ${page * pageSize >= total ? 'bf-btn--disabled' : ''}`}
            onClick={() => page * pageSize < total && setPage(page + 1)}
          >
            下一页
          </View>
        </View>
      )}

      {/* 批量导入弹窗 */}
      {importOpen && (
        <View className='m11-mask' onClick={() => setImportOpen(false)}>
          <View className='m11-modal m11-modal--wide' onClick={(e) => e.stopPropagation()}>
            <Text className='m11-modal__title'>批量导入商机</Text>
            <Text className='bf-muted m11-modal__sub'>
              按模板粘贴 CSV（表头：商机名称,分类,适用城市,资金下限,资金上限,回本周期,毛利率,难度,来源）。粘贴多条时自动拆行。
            </Text>
            <Text className='m11-modal__h'>模板示例（可先复制再粘贴）</Text>
            <Textarea
              className='m11-import__area'
              value={importText}
              onInput={(e) => setImportText(e.detail.value)}
              placeholder={IMPORT_TEMPLATE}
              placeholderClass='bf-muted'
              maxlength={5000}
            />
            <View className={`bf-btn m11-modal__btn ${importBusy ? 'bf-btn--disabled' : ''}`} onClick={() => !importBusy && doImport()}>
              {importBusy ? '正在导入…' : `导入并进入待审核（${parseCsv(importText).length} 条）`}
            </View>
            <View className='bf-btn bf-btn--ghost m11-modal__btn' onClick={() => setImportOpen(false)}>
              取消
            </View>
          </View>
        </View>
      )}

      {/* V5.0 M4-04 版本历史 / 回滚弹窗 */}
      {versionOpen && versionItem && (
        <View className='m11-mask' onClick={() => setVersionOpen(false)}>
          <View className='m11-modal m11-modal--wide' onClick={(e) => e.stopPropagation()}>
            <Text className='m11-modal__title'>版本历史 · {versionItem.title}</Text>
            <Text className='bf-muted m11-modal__sub'>
              保存时自动备份上一版本，支持回滚到任意历史版本；修改后 5 分钟内对用户端生效。
            </Text>
            {versions.length === 0 && <Text className='bf-muted m11-empty-line'>暂无历史版本</Text>}
            {versions.map((v) => (
              <View key={v.version} className='m11-ver-row'>
                <View className='m11-ver-row__main'>
                  <Text className='m11-row__title'>v{v.version}</Text>
                  <Text className='bf-muted m11-row__sub'>{v.title} · {v.updatedAt}</Text>
                </View>
                <View
                  className={`bf-btn bf-btn--sm ${versionBusy ? 'bf-btn--disabled' : ''}`}
                  onClick={() => !versionBusy && doRollback(v.version)}
                >
                  回滚到此版本
                </View>
              </View>
            ))}
            <View className='bf-btn bf-btn--ghost m11-modal__btn' onClick={() => setVersionOpen(false)}>
              关闭
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
