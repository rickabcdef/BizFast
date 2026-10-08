import { useCallback, useEffect, useState } from 'react'
import { View, Text, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Loading from '@/components/Loading'
import ErrorTip from '@/components/ErrorTip'
import {
  exportCsv,
  getAdminOrders,
  processRefund,
  repairOrder,
  resolveAllAbnormalOrders,
  ORDER_ABNORMAL_LABEL,
  type AdminOrder
} from '@/services/bApi'
import type { OrderStatus } from '@/types'

// M11-02 订单管理：查看订单 / 处理退款 / 一键补单 / 批量处理异常 / 导出对账表（V5.0 M4-03）
const STATUS_LABEL: Record<string, string> = {
  '': '全部状态',
  pending: '待支付',
  paid: '已支付',
  generating: '生成中',
  delivered: '已交付',
  refunded: '已退款',
  closed: '已关闭'
}
const STATUS_LIST = Object.keys(STATUS_LABEL)

export default function OrdersView() {
  const [rows, setRows] = useState<AdminOrder[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [onlyAbnormal, setOnlyAbnormal] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [refunding, setRefunding] = useState<AdminOrder | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const abnormalCount = rows.filter((o) => o.abnormal && !o.abnormalHandled).length

  const load = useCallback(
    async (p = page, kw = keyword, st = status, ab = onlyAbnormal) => {
      setLoading(true)
      setError('')
      try {
        const d = await getAdminOrders({ page: p, pageSize, keyword: kw, status: st, abnormal: ab })
        setRows(d.items)
        setTotal(d.total)
      } catch (e: any) {
        setError(e?.message || '订单列表加载失败，请重试')
      } finally {
        setLoading(false)
      }
    },
    [page, keyword, status, onlyAbnormal, pageSize]
  )

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  const doSearch = () => {
    setPage(1)
    void load(1, keyword, status, onlyAbnormal)
  }

  const doExport = () => {
    const ok = exportCsv(
      `生意快启_订单对账表_${Date.now()}.csv`,
      ['订单号', '用户', '套餐', '金额', '状态', '渠道', '下单时间', '支付时间', '已下载', '异常标记', '处理状态', '退款申请'],
      rows.map((o) => [
        o.id,
        o.userPhone,
        o.planName,
        o.amountYuan,
        o.statusLabel,
        o.channel,
        o.createdAt,
        o.paidAt || '',
        o.downloaded ? '是' : '否',
        o.abnormal ? ORDER_ABNORMAL_LABEL[o.abnormalType || ''] || '异常' : '否',
        o.abnormalHandled ? '已处理' : o.abnormal ? '待处理' : '—',
        o.refundRequested ? o.refundReason || '是' : '否'
      ])
    )
    Taro.showToast({ title: ok ? '对账表已导出' : '导出失败，请重试', icon: 'none' })
  }

  const doRefund = async (action: 'approve' | 'reject') => {
    if (!refunding || busy) return
    setBusy(true)
    try {
      const r = await processRefund(refunding.id, action, action === 'reject' ? reason || '运营驳回' : undefined)
      setRefunding(null)
      setReason('')
      Taro.showToast({ title: r.message, icon: 'none' })
      void load()
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '退款处理失败，请重试', icon: 'none' })
    } finally {
      setBusy(false)
    }
  }

  // V5.0 M4-03 一键补单（渠道已扣款但回调丢失 → 主动查单把货补给用户）
  const doRepair = async (o: AdminOrder) => {
    if (busy) return
    setBusy(true)
    try {
      const r = await repairOrder(o.id)
      Taro.showToast({ title: r.message, icon: 'none' })
      void load()
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '补单失败，请重试', icon: 'none' })
    } finally {
      setBusy(false)
    }
  }

  // V5.0 M4-03 一键批量处理异常订单（处理后不再红色高亮，相关告警同步关闭）
  const doResolveAll = async () => {
    if (busy || abnormalCount === 0) {
      if (abnormalCount === 0) Taro.showToast({ title: '当前没有待处理的异常订单', icon: 'none' })
      return
    }
    setBusy(true)
    try {
      const r = await resolveAllAbnormalOrders()
      Taro.showToast({ title: r.message, icon: 'none' })
      void load()
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '批量处理失败，请重试', icon: 'none' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <View className='m11-orders'>
      <View className='bf-card'>
        <View className='bf-row'>
          <Input
            className='bf-input m11-filter__input'
            placeholder='搜索订单号 / 手机号'
            value={keyword}
            onInput={(e) => setKeyword(e.detail.value)}
            onConfirm={doSearch}
          />
          <View className='bf-btn bf-btn--sm' onClick={doSearch}>
            搜索
          </View>
        </View>
        <View className='m11-filter__segs m11-filter__segs--wrap'>
          {STATUS_LIST.map((s) => (
            <View
              key={s}
              className={`m11-seg ${status === s ? 'is-active' : ''}`}
              onClick={() => {
                setStatus(s)
                setPage(1)
                void load(1, keyword, s, onlyAbnormal)
              }}
            >
              {STATUS_LABEL[s]}
            </View>
          ))}
          <View
            className={`m11-seg m11-seg--danger ${onlyAbnormal ? 'is-active' : ''}`}
            onClick={() => {
              setOnlyAbnormal(!onlyAbnormal)
              setPage(1)
              void load(1, keyword, status, !onlyAbnormal)
            }}
          >
            仅看异常{abnormalCount > 0 ? `（${abnormalCount}）` : ''}
          </View>
        </View>
        <View className='bf-row m11-filter__foot'>
          <Text className='bf-muted'>共 {total} 笔订单</Text>
          <View className='bf-btn bf-btn--sm bf-btn--danger' onClick={doResolveAll}>
            一键处理异常
          </View>
          <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={doExport}>
            导出对账表
          </View>
        </View>
      </View>

      {loading && <Loading text='正在加载订单…' />}
      {error && <ErrorTip message={error} onRetry={() => void load()} />}

      {!loading && !error && (
        <View className='bf-card'>
          {rows.map((o) => (
            <View key={o.id} className={`m11-row ${o.abnormal && !o.abnormalHandled ? 'm11-row--abnormal' : ''}`}>
              <View className='m11-row__main'>
                <Text className='m11-row__title'>
                  {o.planName} · {o.id}
                  {o.abnormal && !o.abnormalHandled && (
                    <Text className='m11-tag-danger'>{ORDER_ABNORMAL_LABEL[o.abnormalType || ''] || '异常订单'}</Text>
                  )}
                  {o.abnormalHandled && <Text className='m11-tag-ok'>异常已处理</Text>}
                </Text>
                <Text className='bf-muted m11-row__sub'>
                  {o.userPhone} · {o.channel} · {o.createdAt}
                  {o.downloaded ? ' · 已下载' : ' · 未下载'}
                </Text>
                {o.refundRequested && (
                  <Text className='m11-tip m11-tip--warn'>退款申请：{o.refundReason || '用户申请'}</Text>
                )}
              </View>
              <View className='m11-row__right'>
                <Text className='m11-row__amount'>¥{o.amountYuan}</Text>
                <Text className='bf-tag'>{o.statusLabel}</Text>
                {o.abnormal && !o.abnormalHandled && (
                  <View className='bf-btn bf-btn--sm bf-btn--warn' onClick={() => !busy && doRepair(o)}>
                    一键补单
                  </View>
                )}
                {o.refundRequested && (o.status === 'paid' || o.status === 'generating' || o.status === 'delivered') && (
                  <View className='bf-btn bf-btn--sm bf-btn--ghost' onClick={() => setRefunding(o)}>
                    处理退款
                  </View>
                )}
              </View>
            </View>
          ))}
          {rows.length === 0 && <Text className='bf-muted m11-empty-line'>没有符合条件的订单</Text>}
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

      {/* 退款处理弹窗（M11-02：同意原路退回 / 驳回并记录原因） */}
      {refunding && (
        <View className='m11-mask' onClick={() => setRefunding(null)}>
          <View className='m11-modal' onClick={(e) => e.stopPropagation()}>
            <Text className='m11-modal__title'>处理退款 · {refunding.id}</Text>
            <Text className='bf-muted m11-modal__sub'>
              {refunding.planName} · ¥{refunding.amountYuan} · 申请原因：{refunding.refundReason || '（未填写）'}
            </Text>
            <Text className='m11-modal__h'>驳回原因（驳回时填写）</Text>
            <Input
              className='bf-input m11-modal__input'
              placeholder='如：已交付超 7 天 / 用户重复申请'
              value={reason}
              onInput={(e) => setReason(e.detail.value)}
            />
            <View className={`bf-btn m11-modal__btn ${busy ? 'bf-btn--disabled' : ''}`} onClick={() => !busy && doRefund('approve')}>
              {busy ? '处理中…' : '同意退款（24h 内原路到账）'}
            </View>
            <View className='bf-btn bf-btn--ghost m11-modal__btn' onClick={() => !busy && doRefund('reject')}>
              驳回申请
            </View>
            <View className='bf-btn bf-btn--ghost m11-modal__btn' onClick={() => setRefunding(null)}>
              取消
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
