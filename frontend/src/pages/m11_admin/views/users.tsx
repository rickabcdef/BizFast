import { useCallback, useEffect, useState } from 'react'
import { View, Text, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import { exportCsv, getAdminUserDetail, getAdminUsers, type AdminUser } from '@/services/bApi'

// M11-01 用户管理：列表 / 详情 / 会员状态 / 消费记录，支持筛选与导出
const MEMBER_FILTERS = [
  { value: '', label: '全部' },
  { value: 'none', label: '游客' },
  { value: 'single', label: '单次' },
  { value: 'month', label: '月会员' },
  { value: 'year', label: '年会员' }
]

export default function UsersView() {
  const [rows, setRows] = useState<AdminUser[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [member, setMember] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<{ user: AdminUser; consumption: any[] } | null>(null)

  const load = useCallback(
    async (p = page, kw = keyword, mb = member) => {
      setLoading(true)
      setError('')
      try {
        const d = await getAdminUsers({ page: p, pageSize, keyword: kw, memberStatus: mb })
        setRows(d.items)
        setTotal(d.total)
      } catch (e: any) {
        setError(e?.message || '用户列表加载失败，请重试')
      } finally {
        setLoading(false)
      }
    },
    [page, keyword, member, pageSize]
  )

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  const doSearch = () => {
    setPage(1)
    void load(1, keyword, member)
  }

  const doExport = () => {
    const ok = exportCsv(
      `生意快启_用户列表_${Date.now()}.csv`,
      ['用户ID', '手机号', '昵称', '城市', '会员状态', '订单数', '消费总额', '注册时间', '风控标记'],
      rows.map((u) => [u.id, u.phone, u.nickname, u.city, u.memberLabel, u.orderCount, u.totalSpendYuan, u.createdAt, u.riskFlag ? '是' : '否'])
    )
    Taro.showToast({ title: ok ? '已导出 CSV' : '导出失败，请重试', icon: 'none' })
  }

  const openDetail = async (u: AdminUser) => {
    try {
      const d = await getAdminUserDetail(u.id)
      setDetail(d)
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '详情加载失败', icon: 'none' })
    }
  }

  return (
    <View className='m11-users'>
      <View className='bf-card'>
        <View className='bf-row'>
          <Input
            className='bf-input m11-filter__input'
            placeholder='搜索手机号 / 昵称 / 城市'
            value={keyword}
            onInput={(e) => setKeyword(e.detail.value)}
            onConfirm={doSearch}
          />
          <View className='bf-btn bf-btn--sm' onClick={doSearch}>
            搜索
          </View>
        </View>
        <View className='m11-filter__segs'>
          {MEMBER_FILTERS.map((f) => (
            <View
              key={f.value}
              className={`m11-seg ${member === f.value ? 'is-active' : ''}`}
              onClick={() => {
                setMember(f.value)
                setPage(1)
                void load(1, keyword, f.value)
              }}
            >
              {f.label}
            </View>
          ))}
        </View>
        <View className='bf-row m11-filter__foot'>
          <Text className='bf-muted'>共 {total} 个用户</Text>
          <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={doExport}>
            导出 CSV
          </View>
        </View>
      </View>

      {loading && <Loading text='正在加载用户…' />}
      {error && <ErrorTip message={error} onRetry={() => void load()} />}

      {!loading && !error && (
        <View className='bf-card'>
          {rows.map((u) => (
            <View key={u.id} className='bf-list__item m11-row' onClick={() => void openDetail(u)}>
              <View className='m11-row__main'>
                <Text className='m11-row__title'>
                  {u.nickname}
                  {u.riskFlag && <Text className='m11-risk'>风控</Text>}
                </Text>
                <Text className='bf-muted m11-row__sub'>
                  {u.phone} · {u.city} · 注册 {u.createdAt}
                </Text>
              </View>
              <View className='m11-row__right'>
                <Text className='bf-tag bf-tag--good'>{u.memberLabel}</Text>
                <Text className='bf-muted m11-row__spend'>¥{u.totalSpendYuan}</Text>
              </View>
            </View>
          ))}
          {rows.length === 0 && <Text className='bf-muted m11-empty-line'>没有符合条件的用户</Text>}
        </View>
      )}

      {/* 分页 */}
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

      {/* 用户详情 + 消费记录 */}
      {detail && (
        <View className='m11-mask' onClick={() => setDetail(null)}>
          <View className='m11-modal' onClick={(e) => e.stopPropagation()}>
            <Text className='m11-modal__title'>{detail.user.nickname}</Text>
            <Text className='bf-muted m11-modal__sub'>
              {detail.user.phone} · {detail.user.city} · {detail.user.memberLabel}
            </Text>
            <Text className='bf-muted m11-modal__sub'>
              订单 {detail.user.orderCount} 单 · 累计消费 ¥{detail.user.totalSpendYuan} · 注册 {detail.user.createdAt}
            </Text>
            {detail.user.riskFlag && <Text className='m11-tip m11-tip--warn'>该用户命中风控标记，已转人工审核</Text>}
            <Text className='m11-modal__h'>消费记录</Text>
            <View className='bf-list'>
              {(detail.consumption || []).map((o: any) => (
                <View key={o.id} className='bf-list__item'>
                  <View>
                    <Text>{o.planName}</Text>
                    <Text className='bf-muted'> {o.id}</Text>
                  </View>
                  <Text className='bf-muted'>¥{o.amountYuan}</Text>
                </View>
              ))}
              {(detail.consumption || []).length === 0 && (
                <Text className='bf-muted'>暂无消费记录</Text>
              )}
            </View>
            <View className='bf-btn bf-btn--ghost m11-modal__btn' onClick={() => setDetail(null)}>
              关闭
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
