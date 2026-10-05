import { useState } from 'react'
import { View, Text, Input, Slider, Image } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { compressImage, formatBytes, type ImageFormat } from '@/utils/tools/image'
import { mergePdfs, splitPdf } from '@/utils/tools/pdf'
import { generateQR } from '@/utils/tools/qrcode'
import { generateCopy, countChars, rewriteTone, type CopyInput } from '@/utils/tools/copywriter'
import { saveFile, copyText } from '@/utils/platform'
import ErrorTip from '@/components/ErrorTip'
import './index.scss'

// M6 工具箱 | 负责人: C | 优先级: P1
// M6-01 图片压缩 / M6-02 PDF合并拆分 / M6-03 二维码 / M6-04 文案助手；全部永久免费、本地处理
type ToolKey = 'image' | 'pdf' | 'qrcode' | 'copy'

const TOOLS: { key: ToolKey; icon: string; title: string; desc: string }[] = [
  { key: 'image', icon: '🖼️', title: '图片压缩与格式转换', desc: 'JPG/PNG/WebP 互转，本地处理不上传' },
  { key: 'pdf', icon: '📄', title: 'PDF 合并与拆分', desc: '合并多份、按页码拆分，本地处理' },
  { key: 'qrcode', icon: '📱', title: '二维码生成', desc: '收款码/引流码，自定义颜色与 Logo' },
  { key: 'copy', icon: '✍️', title: '文案小助手', desc: '润色改写、字数统计，一键复制' }
]

function pickFiles(accept: string, multiple = false): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = accept
    input.multiple = multiple
    input.onchange = () => resolve(Array.from(input.files || []))
    input.click()
  })
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  saveFile(url, fileName)
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

export default function M6Tools() {
  const [tool, setTool] = useState<ToolKey>('image')

  return (
    <View className='page m6-tools'>
      <View className='m6-head'>
        <Text className='m6-title'>🛠️ 实用工具箱</Text>
        <Text className='m6-sub'>做生意常用小工具，全部永久免费</Text>
      </View>

      <View className='m6-list'>
        {TOOLS.map((t) => (
          <View
            key={t.key}
            className={`m6-list__item ${tool === t.key ? 'is-active' : ''}`}
            onClick={() => setTool(t.key)}
          >
            <Text className='m6-list__icon'>{t.icon}</Text>
            <View className='m6-list__body'>
              <Text className='m6-list__title'>{t.title}</Text>
              <Text className='m6-list__desc'>{t.desc}</Text>
            </View>
            <Text className='m6-list__arrow'>{tool === t.key ? '︿' : '﹀'}</Text>
          </View>
        ))}
      </View>

      {tool === 'image' && <ImageTool />}
      {tool === 'pdf' && <PdfTool />}
      {tool === 'qrcode' && <QrTool />}
      {tool === 'copy' && <CopyTool />}

      <View className='m6-free'>
        <Text className='m6-free__icon'>🎁</Text>
        <View>
          <Text className='m6-free__title'>全部工具永久免费</Text>
          <Text className='m6-free__desc'>无广告、无次数限制、本地处理不上传隐私</Text>
        </View>
      </View>

      <View className='m6-games'>
        <Text className='m6-games__title'>😌 休息一下</Text>
        <View className='m6-games__row'>
          <View className='m6-games__card' onClick={() => Taro.navigateTo({ url: '/pages/m7_games/index?g=bubble' })}>
            <Text className='m6-games__ico'>🫧</Text>
            <Text className='m6-games__label'>指尖解压</Text>
          </View>
          <View className='m6-games__card' onClick={() => Taro.navigateTo({ url: '/pages/m7_games/index?g=merge' })}>
            <Text className='m6-games__ico'>🔢</Text>
            <Text className='m6-games__label'>数字合成</Text>
          </View>
        </View>
      </View>
    </View>
  )
}

/* ---------------- M6-01 图片压缩 ---------------- */
function ImageTool() {
  const [file, setFile] = useState<File | null>(null)
  const [quality, setQuality] = useState(80)
  const [format, setFormat] = useState<ImageFormat>('keep')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ url: string; size: number; mime: string } | null>(null)

  const choose = async () => {
    const files = await pickFiles('image/png,image/jpeg,image/webp')
    if (files[0]) {
      setFile(files[0])
      setResult(null)
      setError('')
    }
  }

  const run = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const r = await compressImage(file, { quality, format })
      setResult({ url: r.dataUrl, size: r.size, mime: r.mime })
    } catch (e: any) {
      setError(e?.message || '处理失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  const ext = (mime: string) => (mime === 'image/jpeg' ? 'jpg' : mime === 'image/webp' ? 'webp' : 'png')
  const formats: { v: ImageFormat; l: string }[] = [
    { v: 'keep', l: '原格式' },
    { v: 'jpeg', l: 'JPG' },
    { v: 'png', l: 'PNG' },
    { v: 'webp', l: 'WebP' }
  ]

  return (
    <View className='m6-panel bf-card'>
      <View className='m6-drop' onClick={choose}>
        <Text className='m6-drop__ico'>📤</Text>
        <Text className='m6-drop__t'>{file ? file.name : '点击选择图片'}</Text>
        <Text className='m6-drop__s'>支持 JPG / PNG / WebP，单张 ≤ 20MB</Text>
      </View>

      {file && (
        <>
          <View className='m6-slider-label'>
            <Text>压缩质量</Text>
            <Text className='m6-slider-val'>{quality}%</Text>
          </View>
          <Slider min={10} max={100} value={quality} blockSize={20} activeColor='#9b5cff' backgroundColor='rgba(255,255,255,0.15)' onChanging={(e) => setQuality(e.detail.value)} />

          <Text className='m6-subtitle'>输出格式</Text>
          <View className='m6-seg'>
            {formats.map((f) => (
              <View key={f.v} className={`m6-seg__item ${format === f.v ? 'is-active' : ''}`} onClick={() => setFormat(f.v)}>
                <Text>{f.l}</Text>
              </View>
            ))}
          </View>

          {file && !result && (
            <Text className='bf-muted m6-meta'>原图大小：{formatBytes(file.size)}</Text>
          )}

          {error && <ErrorTip message={error} onRetry={run} />}

          <View className={`bf-btn m6-go ${busy ? 'bf-btn--disabled' : ''}`} onClick={() => !busy && run()}>
            {busy ? '处理中…' : '开始压缩'}
          </View>

          {result && (
            <View className='m6-result'>
              <Image className='m6-result__img' src={result.url} mode='widthFix' />
              <Text className='bf-muted m6-meta'>
                已压缩：{formatBytes(result.size)}
                {file && result.size < file.size ? `（省了 ${Math.round((1 - result.size / file.size) * 100)}%）` : ''}
              </Text>
              <View
                className='bf-btn m6-go'
                onClick={() => downloadBlob(new Blob([result.url], { type: result.mime }), `生意快启_压缩图.${ext(result.mime)}`)}
              >
                ⬇️ 下载图片
              </View>
            </View>
          )}
        </>
      )}
    </View>
  )
}

/* ---------------- M6-02 PDF ---------------- */
function PdfTool() {
  const [mode, setMode] = useState<'merge' | 'split'>('merge')
  const [files, setFiles] = useState<File[]>([])
  const [ranges, setRanges] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [mergedUrl, setMergedUrl] = useState<string | null>(null)
  const [splits, setSplits] = useState<{ name: string; url: string }[]>([])

  const chooseMerge = async () => {
    const fs = await pickFiles('application/pdf', true)
    if (fs.length) {
      setFiles(fs)
      setMergedUrl(null)
      setError('')
    }
  }
  const chooseSplit = async () => {
    const fs = await pickFiles('application/pdf', false)
    if (fs[0]) {
      setFiles([fs[0]])
      setSplits([])
      setError('')
    }
  }

  const runMerge = async () => {
    setBusy(true)
    setError('')
    try {
      const blob = await mergePdfs(files)
      setMergedUrl(URL.createObjectURL(blob))
    } catch (e: any) {
      setError(e?.message || '合并失败，请重试')
    } finally {
      setBusy(false)
    }
  }
  const runSplit = async () => {
    setBusy(true)
    setError('')
    try {
      const res = await splitPdfs(files[0], ranges)
      setSplits(res.map((r) => ({ name: r.name, url: URL.createObjectURL(r.blob) })))
    } catch (e: any) {
      setError(e?.message || '拆分失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <View className='m6-panel bf-card'>
      <View className='m6-seg'>
        <View className={`m6-seg__item ${mode === 'merge' ? 'is-active' : ''}`} onClick={() => setMode('merge')}><Text>合并 PDF</Text></View>
        <View className={`m6-seg__item ${mode === 'split' ? 'is-active' : ''}`} onClick={() => setMode('split')}><Text>拆分 PDF</Text></View>
      </View>

      {mode === 'merge' ? (
        <>
          <View className='m6-drop' onClick={chooseMerge}>
            <Text className='m6-drop__ico'>📄</Text>
            <Text className='m6-drop__t'>{files.length ? `已选 ${files.length} 个 PDF` : '点击选择多个 PDF'}</Text>
            <Text className='m6-drop__s'>按选择顺序合并，单文件 ≤ 50MB、≤100 页</Text>
          </View>
          {files.length > 0 && (
            <View className='m6-filelist'>
              {files.map((f, i) => (
                <Text key={i} className='m6-filelist__item'>{i + 1}. {f.name}（{formatBytes(f.size)}）</Text>
              ))}
            </View>
          )}
          {error && <ErrorTip message={error} onRetry={runMerge} />}
          {files.length > 0 && (
            <View className={`bf-btn m6-go ${busy ? 'bf-btn--disabled' : ''}`} onClick={() => !busy && runMerge()}>
              {busy ? '合并中…' : '合并并下载'}
            </View>
          )}
          {mergedUrl && <View className='bf-btn m6-go' onClick={() => saveFile(mergedUrl, '生意快启_合并后.pdf')}>⬇️ 下载合并结果</View>}
        </>
      ) : (
        <>
          <View className='m6-drop' onClick={chooseSplit}>
            <Text className='m6-drop__ico'>✂️</Text>
            <Text className='m6-drop__t'>{files[0]?.name || '点击选择一个 PDF'}</Text>
            <Text className='m6-drop__s'>单文件 ≤ 50MB、≤100 页</Text>
          </View>
          <Text className='m6-subtitle'>页码范围</Text>
          <Input className='bf-input' placeholder='例如：1-3,5,8-10' value={ranges} onInput={(e) => setRanges(e.detail.value)} />
          <Text className='bf-muted m6-meta'>用逗号分隔多个区间，将分别导出</Text>
          {error && <ErrorTip message={error} onRetry={runSplit} />}
          {files[0] && (
            <View className={`bf-btn m6-go ${busy ? 'bf-btn--disabled' : ''}`} onClick={() => !busy && runSplit()}>
              {busy ? '拆分中…' : '开始拆分'}
            </View>
          )}
          {splits.map((s) => (
            <View key={s.name} className='m6-filelist__item m6-filelist__row' onClick={() => saveFile(s.url, s.name)}>
              <Text>{s.name}</Text>
              <Text className='m6-download'>⬇️</Text>
            </View>
          ))}
        </>
      )}
    </View>
  )
}

/* ---------------- M6-03 二维码 ---------------- */
function QrTool() {
  const [text, setText] = useState('')
  const [color, setColor] = useState('#5B6CFF')
  const [logo, setLogo] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [qrUrl, setQrUrl] = useState('')
  const colors = ['#5B6CFF', '#9B5CFF', '#0B1026', '#00B42A', '#FF5C7C']

  const chooseLogo = async () => {
    const fs = await pickFiles('image/png,image/jpeg')
    if (fs[0]) setLogo(fs[0])
  }
  const run = async () => {
    setBusy(true)
    setError('')
    try {
      const url = await generateQR({ text, color, size: 1024, logoFile: logo })
      setQrUrl(url)
    } catch (e: any) {
      setError(e?.message || '生成失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <View className='m6-panel bf-card'>
      <Input className='bf-input' placeholder='输入链接或文字（收款码、微信号、网址…）' value={text} onInput={(e) => setText(e.detail.value)} />
      <Text className='m6-subtitle'>码点颜色</Text>
      <View className='m6-colors'>
        {colors.map((c) => (
          <View key={c} className={`m6-color ${color === c ? 'is-active' : ''}`} style={{ background: c }} onClick={() => setColor(c)} />
        ))}
      </View>
      <View className='m6-row'>
        <Text className='bf-muted'>中心 Logo（可选）</Text>
        <Text className='bf-tag' onClick={chooseLogo}>{logo ? logo.name : '＋ 选择'}</Text>
      </View>
      {error && <ErrorTip message={error} onRetry={run} />}
      <View className={`bf-btn m6-go ${busy ? 'bf-btn--disabled' : ''}`} onClick={() => !busy && run()}>{busy ? '生成中…' : '生成二维码'}</View>
      {qrUrl && (
        <View className='m6-qr'>
          <Image className='m6-qr__img' src={qrUrl} mode='aspectFit' />
          <View className='bf-btn m6-go' onClick={() => saveFile(qrUrl, '生意快启_二维码.png')}>⬇️ 下载高清 PNG</View>
        </View>
      )}
    </View>
  )
}

/* ---------------- M6-04 文案小助手 ---------------- */
function CopyTool() {
  const [input, setInput] = useState<CopyInput>({ category: '', shopName: '', sellingPoint: '', audience: '', tone: 'warm' })
  const [out, setOut] = useState<{ moments: string[]; video: string; promo: string } | null>(null)
  const [error, setError] = useState('')
  const set = (k: keyof CopyInput, v: any) => setInput((p) => ({ ...p, [k]: v }))
  const tones: { v: CopyInput['tone']; l: string }[] = [
    { v: 'warm', l: '温暖' },
    { v: 'professional', l: '专业' },
    { v: 'lively', l: '活泼' }
  ]

  const run = () => {
    setError('')
    if (!input.category.trim() && !input.shopName.trim() && !input.sellingPoint.trim()) {
      setError('至少填写「行业/品类」或「核心卖点」中的一项')
      return
    }
    const r = generateCopy(input)
    setOut({ moments: r.moments, video: r.video, promo: r.promo })
  }

  const CopyBlock = ({ title, text }: { title: string; text: string }) => (
    <View className='m6-copy'>
      <View className='m6-row'>
        <Text className='m6-copy__title'>{title}</Text>
        <Text className='bf-tag m6-copy__count'>{countChars(text)} 字</Text>
      </View>
      <Text className='m6-copy__text'>{text}</Text>
      <View className='m6-row'>
        <Text
          className='bf-tag'
          onClick={async () => {
            const ok = await copyText(text)
            Taro.showToast({ title: ok ? '已复制' : '复制失败，请手动选择', icon: 'none' })
          }}
        >
          📋 复制
        </Text>
        <Text
          className='bf-tag'
          onClick={async () => {
            const rw = rewriteTone(text, input.tone)
            const ok = await copyText(rw)
            Taro.showToast({ title: ok ? `已复制「${input.tone === 'lively' ? '活泼' : input.tone === 'professional' ? '专业' : '温暖'}版」` : '改写失败', icon: 'none' })
          }}
        >
          ✨ 改写并复制
        </Text>
      </View>
    </View>
  )

  return (
    <View className='m6-panel bf-card'>
      <Input className='bf-input m6-field' placeholder='行业/品类（如：社区奶茶店）' value={input.category} onInput={(e) => set('category', e.detail.value)} />
      <Input className='bf-input m6-field' placeholder='店名' value={input.shopName} onInput={(e) => set('shopName', e.detail.value)} />
      <Input className='bf-input m6-field' placeholder='核心卖点（如：当天现做、料足实惠）' value={input.sellingPoint} onInput={(e) => set('sellingPoint', e.detail.value)} />
      <Input className='bf-input m6-field' placeholder='目标人群（如：附近上班族）' value={input.audience} onInput={(e) => set('audience', e.detail.value)} />
      <Text className='m6-subtitle'>语气风格</Text>
      <View className='m6-seg'>
        {tones.map((t) => (
          <View key={t.v} className={`m6-seg__item ${input.tone === t.v ? 'is-active' : ''}`} onClick={() => set('tone', t.v)}><Text>{t.l}</Text></View>
        ))}
      </View>
      {error && <ErrorTip message={error} onRetry={run} />}
      <View className='bf-btn m6-go' onClick={run}>生成文案</View>

      {out && (
        <View>
          {out.moments.map((m, i) => (
            <CopyBlock key={i} title={`朋友圈文案 ${i + 1}`} text={m} />
          ))}
          <CopyBlock title='短视频口播' text={out.video} />
          <CopyBlock title='促销活动' text={out.promo} />
        </View>
      )}
    </View>
  )
}
