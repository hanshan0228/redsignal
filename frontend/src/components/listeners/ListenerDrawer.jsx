import { useState, useRef } from 'react';
import { useApp } from '../../context.jsx';
import { saveConfig, generateListenerProfile, generateProjectPersonas, generateProjectVisualAssets, generateOffersMatrix, aiIngestUrl } from '../../api.js';

const DAYS = [['Mon', 1], ['Tue', 2], ['Wed', 3], ['Thu', 4], ['Fri', 5], ['Sat', 6], ['Sun', 0]];

export default function ListenerDrawer({ listener, onClose }) {
  const { cfg, setCfg, setActiveTab } = useApp();
  const [lst, setLst] = useState({ ...listener });
  const [kwInput, setKwInput] = useState('');
  const [nkwInput, setNkwInput] = useState('');
  const [regexSample, setRegexSample] = useState('');
  const saveTimer = useRef(null);

  // AI Profile Generator states
  const [showAiModal, setShowAiModal] = useState(false);
  const [aiForm, setAiForm] = useState({
    site_name: lst.site_name || '',
    site_description: lst.site_description || '',
    site_url: lst.site_url || '',
    credential_id: lst.ai_credential_id || '',
  });
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');
  const [aiResult, setAiResult] = useState(null);

  // Domain Metapersona states
  const [generatingPersonas, setGeneratingPersonas] = useState(false);
  const [showPersonaModal, setShowPersonaModal] = useState(false);
  const [editingPersonaIndex, setEditingPersonaIndex] = useState(-1);
  const [personaForm, setPersonaForm] = useState({
    key: '',
    label: '',
    name: '',
    tone: '',
    match_keywords: '',
  });

  // Visual Asset Library state
  const [showAssetModal, setShowAssetModal] = useState(false);
  const [editingAssetIndex, setEditingAssetIndex] = useState(-1);
  const [generatingAssets, setGeneratingAssets] = useState(false);
  const [ingestUrlInput, setIngestUrlInput] = useState('');
  const [ingestingUrl, setIngestingUrl] = useState(false);
  const [assetForm, setAssetForm] = useState({
    name: '',
    image_url: '',
    target_url: lst.site_url || '',
    intent_keywords: '',
    citation_source: '',
    caption: '',
  });

  // Offers & Micro-Tools Matrix state
  const [showOfferModal, setShowOfferModal] = useState(false);
  const [editingOfferIndex, setEditingOfferIndex] = useState(-1);
  const [generatingOffers, setGeneratingOffers] = useState(false);
  const [offerForm, setOfferForm] = useState({
    key: '',
    name: '',
    url: lst.site_url || '',
    keywords: '',
  });

  // Accordion state to eliminate crowding & clutter
  const [collapsedSections, setCollapsedSections] = useState({
    personas: true,
    assets: true,
    offers: true,
    regex: false,
    notifications: true,
  });
  const toggleSection = (key) => setCollapsedSections(prev => ({ ...prev, [key]: !prev[key] }));

  const handleGenerateOffersMatrix = async () => {
    if (!lst.site_name && !lst.site_description) {
      alert('请先填写站点名称与功能简介，以便 AI 准确规划高转化落地工具');
      return;
    }
    setGeneratingOffers(true);
    try {
      const res = await generateOffersMatrix({
        site_name: lst.site_name || lst.name || 'Product',
        site_description: lst.site_description || 'Technical product & lookup resource',
        site_url: lst.site_url || '',
        keywords: lst.keywords || [],
        credential_id: lst.ai_credential_id || '',
      });
      if (res.ok && res.offers_matrix?.length) {
        update('offers_matrix', res.offers_matrix);
      } else {
        alert(res.error || '推演落地工具矩阵失败');
      }
    } catch (err) {
      alert('网络请求异常: ' + err.message);
    } finally {
      setGeneratingOffers(false);
    }
  };

  const handleLoadDefaultOffers = () => {
    const base = (lst.site_url || 'https://fairwayfort.com').replace(/\/+$/, '');
    const defaultOffers = [
      {
        key: 'serial_decoder',
        name: '车架号与年份解码工具',
        keywords: ['vin', 'serial', 'serial number', 'year', 'what year', 'model number', 'what model', 'which model'],
        url: `${base}/pages/tools?tool=serial-decoder`
      },
      {
        key: 'street_legal',
        name: '全美各州路权合规核查器',
        keywords: ['street legal', 'lsv', 'dmv', 'law', 'legal', 'road', 'public road', 'plate', 'license', 'inspection', 'title', 'statute', 'fmvss', 'as4', 'as5'],
        url: `${base}/pages/tools?tool=street-legal-checker`
      },
      {
        key: 'speed_calc',
        name: '极速与速比在线计算器',
        keywords: ['speed', 'mph', 'fast', 'speed code', 'navitas', 'controller', 'gear', 'rpm', 'speedometer', 'top speed'],
        url: `${base}/pages/tools?tool=speed-calculator`
      },
      {
        key: 'battery_guide',
        name: '锂电换装选型与续航表',
        keywords: ['lithium', 'battery', 'batteries', '36v', '48v', 'lead acid', 'drop in', 'trojan', 'charger', 'bms', 'range'],
        url: `${base}/pages/tools?tool=battery-comparison`
      }
    ];
    update('offers_matrix', defaultOffers);
  };

  const handleOpenAddOffer = () => {
    setEditingOfferIndex(-1);
    setOfferForm({
      key: '',
      name: '',
      url: lst.site_url || '',
      keywords: '',
    });
    setShowOfferModal(true);
  };

  const handleEditOffer = (index) => {
    const o = (lst.offers_matrix || [])[index];
    if (!o) return;
    setEditingOfferIndex(index);
    setOfferForm({
      key: o.key || '',
      name: o.name || '',
      url: o.url || lst.site_url || '',
      keywords: Array.isArray(o.keywords) ? o.keywords.join(', ') : (o.keywords || ''),
    });
    setShowOfferModal(true);
  };

  const handleSaveOffer = () => {
    if (!offerForm.name.trim()) {
      alert('请填写工具/Offer 名称');
      return;
    }
    const kws = offerForm.keywords.split(/[,，\s]+/).map(k => k.trim()).filter(Boolean);
    const newOffer = {
      key: offerForm.key.trim() || `tool_${Date.now()}`,
      name: offerForm.name.trim(),
      url: offerForm.url.trim() || lst.site_url || '',
      keywords: kws,
    };

    const currentOffers = [...(lst.offers_matrix || [])];
    if (editingOfferIndex >= 0) {
      currentOffers[editingOfferIndex] = newOffer;
    } else {
      currentOffers.push(newOffer);
    }
    update('offers_matrix', currentOffers);
    setShowOfferModal(false);
  };

  const handleDeleteOffer = (index) => {
    const nextOffers = (lst.offers_matrix || []).filter((_, idx) => idx !== index);
    update('offers_matrix', nextOffers);
  };

  const handleGenerateVisualAssets = async () => {
    if (!lst.site_name && !lst.site_description) {
      alert('请先填写站点名称与功能简介，以便 AI 准确规划专业图表资产');
      return;
    }
    setGeneratingAssets(true);
    try {
      const res = await generateProjectVisualAssets({
        site_name: lst.site_name || lst.name || 'Product',
        site_description: lst.site_description || 'Technical product & lookup resource',
        site_url: lst.site_url || '',
        keywords: lst.keywords || [],
        credential_id: lst.ai_credential_id || '',
      });
      if (res.ok && res.visual_assets?.length) {
        update('visual_assets', res.visual_assets);
      } else {
        alert(res.error || '推演图表资产失败');
      }
    } catch (err) {
      alert('网络请求异常: ' + err.message);
    } finally {
      setGeneratingAssets(false);
    }
  };

  const handleIngestUrl = async () => {
    if (!ingestUrlInput.trim()) return;
    setIngestingUrl(true);
    try {
      const res = await aiIngestUrl({
        url: ingestUrlInput.trim(),
        platform: lst.platform || 'reddit',
        credential_id: lst.ai_credential_id || '',
      });
      if (res.ok && res.data) {
        const d = res.data;
        const next = {
          ...lst,
          site_name: d.site_name || lst.site_name,
          site_description: d.site_description || lst.site_description,
          site_url: d.site_url || lst.site_url,
          name: d.name || lst.name,
          subreddits: d.subreddits !== undefined ? d.subreddits : lst.subreddits,
          keywords: Array.isArray(d.keywords) && d.keywords.length ? d.keywords : lst.keywords,
          negative_keywords: Array.isArray(d.negative_keywords) && d.negative_keywords.length ? d.negative_keywords : lst.negative_keywords,
          pitch_instruction: d.pitch_instruction || lst.pitch_instruction,
          stealth_mode: d.stealth_mode || (lst.platform === 'x' ? 'profile_only' : 'brand_search'),
          anti_ban_mode: d.anti_ban_mode || (lst.platform === 'x' ? 'brand_search' : 'adaptive'),
          reply_cooldown_minutes: d.reply_cooldown_minutes || (lst.platform === 'x' ? 45 : 30),
          daily_reply_limit: d.daily_reply_limit || (lst.platform === 'x' ? 6 : 12),
          filters: [
            {
              name: 'AI 意向精准初筛',
              prompt: d.filter_prompt || `Does this post indicate the author has an active commercial problem, technical roadblock, or purchasing dilemma that ${d.site_name || 'this product'} solves? Reply YES if relevant to engage or solve a problem, NO if generic news, entertainment, job seeking, consumer complaint, or spam.`,
              enabled: true,
            },
          ],
          personas: Array.isArray(d.personas) && d.personas.length ? d.personas : lst.personas,
          visual_assets: Array.isArray(d.visual_assets) && d.visual_assets.length ? d.visual_assets : lst.visual_assets,
          offers_matrix: Array.isArray(d.offers_matrix) && d.offers_matrix.length ? d.offers_matrix : lst.offers_matrix,
        };
        setLst(next);
        persist(next);
        setIngestUrlInput('');
      } else {
        alert(res.error || 'URL 解析生成失败，请确认网址可访问');
      }
    } catch (err) {
      alert('请求发生错误: ' + err.message);
    } finally {
      setIngestingUrl(false);
    }
  };

  const handleOpenAddAsset = () => {
    setEditingAssetIndex(-1);
    setAssetForm({
      name: '',
      image_url: '',
      target_url: lst.site_url || '',
      intent_keywords: '',
      citation_source: lst.site_name ? `Source: ${lst.site_name} Technical Research` : '',
      caption: '',
    });
    setShowAssetModal(true);
  };

  const handleEditAsset = (index) => {
    const a = (lst.visual_assets || [])[index];
    if (!a) return;
    setEditingAssetIndex(index);
    setAssetForm({
      name: a.name || '',
      image_url: a.image_url || '',
      target_url: a.target_url || lst.site_url || '',
      intent_keywords: Array.isArray(a.intent_keywords) ? a.intent_keywords.join(', ') : (a.intent_keywords || ''),
      citation_source: a.citation_source || '',
      caption: a.caption || '',
    });
    setShowAssetModal(true);
  };

  const handleSaveAsset = () => {
    if (!assetForm.name.trim() || !assetForm.image_url.trim()) return;
    const kws = assetForm.intent_keywords.split(/[,，\s]+/).map(k => k.trim()).filter(Boolean);
    const newAsset = {
      id: editingAssetIndex >= 0 ? ((lst.visual_assets || [])[editingAssetIndex]?.id || `va-${Date.now()}`) : `va-${Date.now()}`,
      name: assetForm.name.trim(),
      image_url: assetForm.image_url.trim(),
      target_url: assetForm.target_url.trim() || lst.site_url || '',
      intent_keywords: kws,
      citation_source: assetForm.citation_source.trim(),
      caption: assetForm.caption.trim() || assetForm.name.trim(),
    };

    const currentAssets = [...(lst.visual_assets || [])];
    if (editingAssetIndex >= 0) {
      currentAssets[editingAssetIndex] = newAsset;
    } else {
      currentAssets.push(newAsset);
    }
    update('visual_assets', currentAssets);
    setShowAssetModal(false);
  };

  const handleDeleteAsset = (index) => {
    const nextAssets = (lst.visual_assets || []).filter((_, idx) => idx !== index);
    update('visual_assets', nextAssets);
  };

  const handleLoadDefaultAssets = () => {
    const defaultAssets = [
      {
        id: 'va-state-matrix',
        name: '50-State Street-Legal Compliance Matrix',
        image_url: 'https://fairwayfort.com/cdn/shop/files/50-state-golf-cart-street-legal-matrix.webp',
        target_url: lst.site_url || 'https://fairwayfort.com/pages/tools',
        intent_keywords: ['state', 'law', 'legal', 'dmv', 'street', 'fl', 'florida', 'ca', 'california', 'tx', 'texas', 'sc', 'nc', 'az', 'arizona', 'ga', 'georgia', 'speed', 'road', 'public', 'highway', 'title', 'plate', 'registration'],
        citation_source: 'Source: NHTSA 49 CFR § 571.500 & State DOT Statutory Frameworks (Fairway Fort Dataset)',
        caption: 'Complete 50-State Golf Cart vs. Low-Speed Vehicle (LSV) Equipment & Speed Limit Matrix.',
      },
      {
        id: 'va-vin-decoder',
        name: 'Golf Cart / LSV VIN & Serial Decoder Chart',
        image_url: 'https://fairwayfort.com/cdn/shop/files/golf-cart-serial-number-location-guide.webp',
        target_url: lst.site_url || 'https://fairwayfort.com/pages/tools',
        intent_keywords: ['vin', 'serial', 'year', 'model', 'identify', 'find', 'decoder', 'chassis', 'club car', 'ezgo', 'yamaha', 'icon', 'precedent', 'ds', 'txt', 'rxv', 'drive', 'g29'],
        citation_source: 'Source: Manufacturer Technical Service Bulletins & Fairway Fort Lookup System',
        caption: 'OEM Serial & 17-digit VIN Placement & Model Year Cross-Reference Chart.',
      },
      {
        id: 'va-windshield-spec',
        name: 'FMVSS 205 Windshield & Safety Equipment Spec Sheet',
        image_url: 'https://fairwayfort.com/cdn/shop/files/dot-approved-windshield-compliance-specs.webp',
        target_url: lst.site_url || 'https://fairwayfort.com/pages/tools',
        intent_keywords: ['windshield', 'dot', 'as4', 'as5', 'acrylic', 'glass', 'polycarbonate', 'wiper', 'fold down', 'split windshield', 'tinted'],
        citation_source: 'Source: DOT FMVSS 205 / ANSI Z26.1 Compliance Standard',
        caption: 'AS4/AS5 Certified Windshield vs Acrylic Fold-Down Street Compliance Comparison.',
      },
      {
        id: 'va-battery-conversion',
        name: '36V to 48V Lithium Conversion & Wiring Schematic',
        image_url: 'https://fairwayfort.com/cdn/shop/files/golf-cart-36v-48v-lithium-conversion-wiring.webp',
        target_url: lst.site_url || 'https://fairwayfort.com/pages/tools',
        intent_keywords: ['battery', 'lithium', 'lifepo4', '36v', '48v', 'voltage', 'charge', 'charger', 'solenoid', 'convert', 'conversion', 'trojan', 'lead acid', 'bms', 'wire', 'wiring', 'series', 'parallel', 'amp', 'ah'],
        citation_source: 'Source: SAE J1798 Battery Safety Standard & Fairway Fort Technical Bulletins',
        caption: 'OEM Battery Bank Series/Parallel vs. Drop-in LiFePO4 Voltage & Solenoid Wiring Diagram.',
      },
      {
        id: 'va-controller-pinout',
        name: 'Curtis / Navitas / Alltrax Motor Controller Pinout Guide',
        image_url: 'https://fairwayfort.com/cdn/shop/files/curtis-navitas-controller-pinout-guide.webp',
        target_url: lst.site_url || 'https://fairwayfort.com/pages/tools',
        intent_keywords: ['controller', 'curtis', 'navitas', 'alltrax', 'motor', 'pinout', 'throttle', 'its', 'solenoid', 'clicking', 'wont run', 'no move', 'beeping', 'diagnostic', 'regen', 'speed code', 'shunts'],
        citation_source: 'Source: OEM Motor Controller Technical Reference Guide (Fairway Fort Dataset)',
        caption: 'High-Current Motor Controller Throttle Input (ITS/0-5kΩ) & Diagnostic Blink Code Matrix.',
      },
      {
        id: 'va-liftkit-tire-fitment',
        name: 'Lift Kit & Tire Clearance Fitment Matrix',
        image_url: 'https://fairwayfort.com/cdn/shop/files/golf-cart-lift-kit-tire-fitment-chart.webp',
        target_url: 'https://fairwayfort.com/pages/fitment-guide',
        intent_keywords: ['lift', 'lift kit', 'tire', 'tires', 'wheel', 'wheels', 'rubbing', 'clearance', 'spindle', 'a-arm', 'all terrain', '14 inch', '12 inch', '10 inch', 'offset', 'camber', 'toe in'],
        citation_source: 'Source: SEMA LSV Suspension Geometry Guidelines & Fairway Fort Fitment Chart',
        caption: 'Drop Spindle vs A-Arm Lift Height (3" to 6") & Max Tire Size Offset Clearance Guide.',
      },
      {
        id: 'va-street-equipment-checklist',
        name: 'Federal DOT Street-Legal Equipment Checklist',
        image_url: 'https://fairwayfort.com/cdn/shop/files/golf-cart-street-legal-equipment-checklist.webp',
        target_url: lst.site_url || 'https://fairwayfort.com/pages/tools',
        intent_keywords: ['checklist', 'equipment', 'turn signal', 'horn', 'seat belt', 'mirror', 'dot tires', 'brake lights', 'inspection', 'sheriff', 'police', 'ticket', 'street legal kit', 'light kit'],
        citation_source: 'Source: Federal Motor Vehicle Safety Standards (NHTSA 49 CFR Part 571 Subpart B)',
        caption: 'Mandatory Equipment Checklist: DOT Tires, Seat Belts, Turn Signals, Mirrors, Horn & Backup Alarm.',
      }
    ];
    update('visual_assets', defaultAssets);
  };

  const handleAiGeneratePersonas = async () => {
    if (!lst.site_name && !lst.site_description) {
      alert('请先填写下方的「站点/产品名称」与「核心功能简介」，AI 才能据此定制专属人设！');
      return;
    }
    setGeneratingPersonas(true);
    try {
      const res = await generateProjectPersonas({
        site_name: lst.site_name || 'My Product',
        site_description: lst.site_description || '',
        keywords: lst.keywords || [],
        pitch_instruction: lst.pitch_instruction || '',
        subreddits: lst.subreddits || '',
        credential_id: lst.ai_credential_id || undefined,
      });
      if (res && res.ok && Array.isArray(res.personas) && res.personas.length > 0) {
        update('personas', res.personas);
        alert(`🎉 成功基于 ${lst.site_name || '新赛道'} AI 推演出 ${res.personas.length} 大专属社区专家人设！`);
      } else {
        alert(`推演失败: ${res?.error || '未能生成有效人设'}`);
      }
    } catch (e) {
      alert(`推演请求异常: ${e.message}`);
    } finally {
      setGeneratingPersonas(false);
    }
  };

  const handleOpenAddPersona = () => {
    setEditingPersonaIndex(-1);
    setPersonaForm({
      key: '',
      label: '',
      name: '',
      tone: '',
      match_keywords: '',
    });
    setShowPersonaModal(true);
  };

  const handleEditPersona = (index) => {
    const p = (lst.personas || [])[index];
    if (!p) return;
    setEditingPersonaIndex(index);
    setPersonaForm({
      key: p.key || '',
      label: p.label || '',
      name: p.name || '',
      tone: p.tone || '',
      match_keywords: Array.isArray(p.match_keywords) ? p.match_keywords.join(', ') : (p.match_keywords || ''),
    });
    setShowPersonaModal(true);
  };

  const handleSavePersona = () => {
    if (!personaForm.label.trim() || !personaForm.tone.trim()) return;
    const kws = personaForm.match_keywords.split(/[,，\s]+/).map(k => k.trim()).filter(Boolean);
    const keySlug = personaForm.key.trim() || personaForm.name.toLowerCase().replace(/[^a-z0-9_]/g, '_') || `persona_${Date.now()}`;
    const newPersona = {
      key: keySlug,
      label: personaForm.label.trim(),
      name: personaForm.name.trim() || personaForm.label.trim(),
      tone: personaForm.tone.trim(),
      match_keywords: kws,
    };

    const currentPersonas = [...(lst.personas || [])];
    if (editingPersonaIndex >= 0) {
      currentPersonas[editingPersonaIndex] = newPersona;
    } else {
      currentPersonas.push(newPersona);
    }
    update('personas', currentPersonas);
    setShowPersonaModal(false);
  };

  const handleDeletePersona = (index) => {
    const nextPersonas = (lst.personas || []).filter((_, idx) => idx !== index);
    update('personas', nextPersonas);
  };

  const handleLoadDefaultGolfPersonas = () => {
    const defaults = [
      {
        key: 'mechanic',
        label: '🔧 驻厂老技师',
        name: 'Senior Master Cart Tech & Diagnostic Guru',
        tone: 'Direct, hands-on, zero fluff. Diagnoses root causes with technical specifics (voltages, pinouts, solenoid clicks, OBC bypasses, motor winding resistance). Speaks from 15+ years in cart repair bays.',
        match_keywords: ['wiring', 'solenoid', 'controller', 'pinout', 'curtis', 'alltrax', 'lithium', 'battery', 'batteries', '36v', '48v', 'charger', 'obc', 'fuse', 'clicking', 'wont run', 'won\'t run', 'motor', 'smoke', 'spark', 'resistor', 'diode', 'throttle', 'its', 'shunts', 'voltage drop', 'bms', 'diagnostic']
      },
      {
        key: 'modder',
        label: '⚡ 极客改装先锋',
        name: 'Performance Builder & Suspension Modder',
        tone: 'Performance enthusiast passionate about speed codes, Navitas 600A OTF on-the-fly programmers, lithium high-discharge C-rates, drop spindle vs A-arm suspension geometry, and tire rubbing clearance offsets. Energetic, tech-savvy, hands-on.',
        match_keywords: ['lift', 'lift kit', 'tire', 'tires', 'wheel', 'wheels', 'rubbing', 'spindle', 'a-arm', 'navitas', 'speed', 'mph', 'fast', 'all-terrain', 'offset', 'camber', 'controller tuning', 'otf', 'high speed', 'gears', 'motor swap']
      },
      {
        key: 'cruiser',
        label: '⛳ 车友会老司机',
        name: 'Neighborhood Cart Veteran & Community Cruiser',
        tone: 'Friendly, seasoned golf cart community regular who cruises daily in golf cart-friendly towns (The Villages, Peachtree City, Sun City, Florida coastal towns). Empathic, practical, expert in daily community use, DOT equipment like mirrors, turn signals, seat belts, and child safety.',
        match_keywords: ['neighborhood', 'village', 'cruiser', 'kids', 'seat belt', 'mirror', 'horn', 'light kit', 'accessories', 'enclosure', 'sound bar', 'speaker', 'cover', 'which cart', 'recommendation', 'buying', 'club car vs ezgo', 'family', 'golf course', 'daily', 'commute']
      },
      {
        key: 'compliance',
        label: '📜 合规与法规专家',
        name: 'Statutory & DMV LSV Compliance Specialist',
        tone: 'Clear, meticulous, well-versed in NHTSA 49 CFR § 571.500, state statutory codes, DMV inspection requirements, FMVSS 205 AS4/AS5 windshield standards vs fold-down acrylic, and 17-digit VIN vs manufacturer serials. Objective, direct, reassuring.',
        match_keywords: ['law', 'legal', 'dmv', 'police', 'sheriff', 'ticket', 'street legal', 'statute', 'inspection', 'title', 'plate', 'registration', 'fmvss', 'as4', 'as5', 'vin', 'serial', 'speed limit', 'road', 'public', 'ordinance']
      }
    ];
    update('personas', defaults);
  };

  const rCreds = (cfg.credentials || []).filter(c => c.type === 'reddit');
  const xCreds = (cfg.credentials || []).filter(c => c.type === 'x' || c.type === 'twitter');
  const forumCreds = (cfg.credentials || []).filter(c => c.type === 'forum' || c.type === 'vbulletin' || c.type === 'phpbb' || c.type === 'xenforo');
  const aiCreds = (cfg.credentials || []).filter(c => ['anthropic', 'openai', 'ollama'].includes(c.type));
  const isX = (lst.platform === 'x' || lst.platform === 'twitter');
  const isForum = (lst.platform === 'forum' || lst.platform === 'vbulletin' || lst.platform === 'phpbb' || lst.platform === 'xenforo');
  const isReddit = !isX && !isForum;

  const handleSelectPlatform = (plat) => {
    let next = { ...lst, platform: plat };
    if (plat === 'x') {
      next.reply_cooldown_minutes = lst.reply_cooldown_minutes || 45;
      next.daily_reply_limit = lst.daily_reply_limit || 6;
      next.stealth_mode = lst.stealth_mode || 'profile_only';
      next.anti_ban_mode = lst.anti_ban_mode || 'brand_search';
    } else if (plat === 'forum') {
      next.forum_rss_url = lst.forum_rss_url || 'https://www.buggiesgonewild.com/external.php?type=RSS2';
      next.reply_cooldown_minutes = lst.reply_cooldown_minutes || 30;
      next.daily_reply_limit = lst.daily_reply_limit || 10;
      next.stealth_mode = lst.stealth_mode || 'profile_only';
      next.anti_ban_mode = lst.anti_ban_mode || 'brand_search';
    } else {
      next.reply_cooldown_minutes = lst.reply_cooldown_minutes || 30;
      next.daily_reply_limit = lst.daily_reply_limit || 10;
      next.stealth_mode = lst.stealth_mode || 'brand_search';
      next.anti_ban_mode = lst.anti_ban_mode || 'adaptive';
    }
    setLst(next);
    persist(next);
  };

  const getFrequencyPresets = () => {
    if (isX) {
      return [
        { id: 'safe', label: '🛡️ 安全低频', cd: 60, limit: 4, tag: '极低风险', desc: '间隔 60m · 每日 4条 (新号冷启动)' },
        { id: 'balanced', label: '⚖️ 稳健推荐', cd: 45, limit: 6, tag: '推荐标杆', desc: '间隔 45m · 每日 6条 (标准商业雷达)' },
        { id: 'active', label: '🚀 活跃冲刺', cd: 30, limit: 10, tag: '适度加速', desc: '间隔 30m · 每日 10条 (蓝V认证号)' },
      ];
    }
    if (isForum) {
      return [
        { id: 'safe', label: '🛡️ 稳妥养号', cd: 45, limit: 5, tag: '低频', desc: '间隔 45m · 每日 5条' },
        { id: 'balanced', label: '⚖️ 行业专家', cd: 30, limit: 10, tag: '推荐', desc: '间隔 30m · 每日 10条' },
        { id: 'active', label: '🚀 密集讨论', cd: 20, limit: 15, tag: '高效', desc: '间隔 20m · 每日 15条' },
      ];
    }
    return [
      { id: 'safe', label: '🛡️ 安全防删', cd: 45, limit: 6, tag: '低Karma推荐', desc: '间隔 45m · 每日 6条 (Karma < 100 账号)' },
      { id: 'balanced', label: '⚖️ 稳健自然', cd: 30, limit: 10, tag: '标准推荐', desc: '间隔 30m · 每日 10条 (自然真实互动)' },
      { id: 'active', label: '🚀 垂类高频', cd: 20, limit: 15, tag: '老号适用', desc: '间隔 20m · 每日 15条 (高活跃垂类)' },
    ];
  };

  const stepCooldown = (delta) => {
    const cur = lst.reply_cooldown_minutes ?? (isX ? 45 : 30);
    const nextVal = Math.max(5, Math.min(240, cur + delta));
    update('reply_cooldown_minutes', nextVal);
  };

  const stepLimit = (delta) => {
    const cur = lst.daily_reply_limit ?? (isX ? 6 : 10);
    const nextVal = Math.max(1, Math.min(50, cur + delta));
    update('daily_reply_limit', nextVal);
  };

  const applyPreset = (preset) => {
    const next = {
      ...lst,
      reply_cooldown_minutes: preset.cd,
      daily_reply_limit: preset.limit,
    };
    setLst(next);
    persist(next);
  };

  const openAiModal = () => {
    setAiForm({
      site_name: lst.site_name || '',
      site_description: lst.site_description || '',
      site_url: lst.site_url || '',
      credential_id: lst.ai_credential_id || '',
    });
    setAiError('');
    setAiResult(null);
    setShowAiModal(true);
  };

  const handleAiGenerate = async () => {
    if (!aiForm.site_name.trim() || !aiForm.site_description.trim()) {
      setAiError('请填写产品名称与核心功能简介');
      return;
    }
    setAiLoading(true);
    setAiError('');
    try {
      const res = await generateListenerProfile({
        site_name: aiForm.site_name.trim(),
        site_description: aiForm.site_description.trim(),
        site_url: aiForm.site_url.trim(),
        platform: lst.platform || 'reddit',
        credential_id: aiForm.credential_id || undefined,
      });
      if (res && res.ok && res.data) {
        setAiResult(res.data);
      } else {
        setAiError(res?.error || 'AI 画像生成失败，请检查 AI 密钥配置');
      }
    } catch (e) {
      setAiError(`生成请求异常: ${e.message}`);
    } finally {
      setAiLoading(false);
    }
  };

  const handleApplyProfile = () => {
    if (!aiResult) return;
    const updated = {
      ...lst,
      name: aiResult.name || lst.name,
      site_name: aiForm.site_name.trim(),
      site_description: aiForm.site_description.trim(),
      site_url: aiForm.site_url.trim(),
      subreddits: aiResult.subreddits !== undefined ? aiResult.subreddits : lst.subreddits,
      keywords: Array.isArray(aiResult.keywords) && aiResult.keywords.length ? aiResult.keywords : lst.keywords,
      negative_keywords: Array.isArray(aiResult.negative_keywords) && aiResult.negative_keywords.length ? aiResult.negative_keywords : lst.negative_keywords,
      pitch_instruction: aiResult.pitch_instruction || lst.pitch_instruction,
      stealth_mode: aiResult.stealth_mode || (lst.platform === 'x' ? 'profile_only' : 'brand_search'),
      anti_ban_mode: aiResult.anti_ban_mode || (lst.platform === 'x' ? 'brand_search' : 'adaptive'),
      reply_cooldown_minutes: aiResult.reply_cooldown_minutes || (lst.platform === 'x' ? 45 : 30),
      daily_reply_limit: aiResult.daily_reply_limit || (lst.platform === 'x' ? 6 : 12),
      filters: [
        {
          name: 'AI 意向精准初筛',
          prompt: aiResult.filter_prompt || `Does this post indicate the author has an active commercial problem, technical roadblock, or purchasing dilemma that ${aiForm.site_name}? Reply YES if relevant to engage or solve a problem, NO if generic news, entertainment, job seeking, consumer complaint, or spam.`,
          enabled: true,
        },
      ],
      ai_credential_id: aiForm.credential_id || lst.ai_credential_id,
      visual_assets: (Array.isArray(aiResult.visual_assets) && aiResult.visual_assets.length) ? aiResult.visual_assets : lst.visual_assets,
      personas: (Array.isArray(aiResult.personas) && aiResult.personas.length) ? aiResult.personas : lst.personas,
      offers_matrix: (Array.isArray(aiResult.offers_matrix) && aiResult.offers_matrix.length) ? aiResult.offers_matrix : lst.offers_matrix,
    };
    setLst(updated);
    persist(updated);
    setShowAiModal(false);
    setAiResult(null);
  };

  const persist = (updated) => {
    const listeners = (cfg.listeners || []).map(l => l.id === updated.id ? updated : l);
    const newCfg = { ...cfg, listeners };
    setCfg(newCfg);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => saveConfig(newCfg), 600);
  };

  const update = (key, val) => {
    const next = { ...lst, [key]: val };
    setLst(next);
    persist(next);
  };

  const updateMulti = (fields) => {
    const next = { ...lst, ...fields };
    setLst(next);
    persist(next);
  };

  const addKw = () => {
    const val = kwInput.trim();
    if (!val) return;
    update('keywords', [...(lst.keywords || []), val]);
    setKwInput('');
  };

  const removeKw = (i) => {
    const kws = [...(lst.keywords || [])];
    kws.splice(i, 1);
    update('keywords', kws);
  };

  const addNkw = () => {
    const val = nkwInput.trim();
    if (!val) return;
    update('negative_keywords', [...(lst.negative_keywords || []), val]);
    setNkwInput('');
  };

  const removeNkw = (i) => {
    const kws = [...(lst.negative_keywords || [])];
    kws.splice(i, 1);
    update('negative_keywords', kws);
  };

  const addFilter = () => {
    const filters = [...(lst.filters || [])];
    filters.push({ name: `Step ${filters.length + 1}`, prompt: 'Is this post from someone who could benefit from our product? Reply YES if relevant, NO if not.', enabled: true });
    update('filters', filters);
  };

  const removeFilter = (i) => {
    const filters = [...(lst.filters || [])];
    filters.splice(i, 1);
    update('filters', filters);
  };

  const updateFilter = (i, key, val) => {
    const filters = (lst.filters || []).map((f, idx) => idx === i ? { ...f, [key]: val } : f);
    update('filters', filters);
  };

  const toggleDay = (day) => {
    const days = Array.isArray(lst.schedule_days) ? [...lst.schedule_days] : [0, 1, 2, 3, 4, 5, 6];
    const idx = days.indexOf(day);
    if (idx >= 0) days.splice(idx, 1); else days.push(day);
    update('schedule_days', days);
  };

  const testRegex = () => {
    const kws = (lst.keywords || []).filter(k => k.trim());
    if (!kws.length || !regexSample) return null;
    try {
      const pat = new RegExp('(?<![A-Za-z0-9])(?:' + kws.join('|') + ')(?![A-Za-z0-9])', 'gi');
      const matches = [...regexSample.matchAll(pat)];
      if (!matches.length) return <span className="text-slate-400">No matches.</span>;
      const hi = regexSample.replace(pat, m => `<mark class="bg-amber-200 text-amber-900 rounded px-0.5 font-medium">${m}</mark>`);
      return <>
        <div className="text-emerald-600 font-semibold mb-1.5">{matches.length} match{matches.length !== 1 ? 'es' : ''}</div>
        <div className="text-slate-600 leading-relaxed" dangerouslySetInnerHTML={{ __html: hi }} />
      </>;
    } catch (e) {
      return <span className="text-red-400 text-xs">Regex error: {e.message}</span>;
    }
  };

  const currentCd = lst.reply_cooldown_minutes ?? (isX ? 45 : 30);
  const currentLimit = lst.daily_reply_limit ?? (isX ? 6 : 10);
  const presets = getFrequencyPresets();
  const matchedPreset = presets.find(p => p.cd === currentCd && p.limit === currentLimit);

  const S = ({ children }) => <div className="text-xs font-semibold text-slate-400 uppercase tracking-widest">{children}</div>;

  return (
    <>
      <div className="hidden fixed inset-0 z-40" style={{ background: 'rgba(15,23,42,.2)', backdropFilter: 'blur(2px)' }} onClick={onClose} />
      <div className="fixed top-0 right-0 h-full w-full max-w-xl bg-white z-50 flex flex-col" style={{ boxShadow: '-8px 0 40px rgba(15,23,42,.12)' }}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold text-slate-900">{lst.name}</h2>
            <span className={`text-[11px] px-2 py-0.5 rounded font-semibold uppercase ${isForum ? 'bg-emerald-100 text-emerald-800 border border-emerald-300' : isX ? 'bg-black text-white' : 'bg-orange-100 text-orange-700'}`}>
              {isForum ? '🌐 垂直技术论坛' : isX ? '𝕏 Radar' : 'Reddit'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors text-xl leading-none">×</button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-7">

          {/* Quick AI Profile Generator & 1-Click URL Ingestion */}
          <div className="bg-gradient-to-br from-violet-600 via-indigo-600 to-blue-700 rounded-2xl p-4 text-white shadow-md space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-base">🚀</span>
                <span className="text-xs font-bold tracking-wide uppercase">AI 一键极速建仓 (Zero-Touch Ingestion)</span>
              </div>
              <button
                type="button"
                onClick={openAiModal}
                className="text-[11px] text-violet-200 hover:text-white underline font-medium"
              >
                手动填写参数推演 →
              </button>
            </div>
            <p className="text-[11px] text-violet-100/90 leading-relaxed">
              输入独立站或产品官网链接，AI 自动抓取并推演精准风控策略、人设矩阵与落地工具！
            </p>
            <div className="flex items-center gap-2 pt-0.5">
              <input
                className="flex-1 px-3 py-2 text-xs bg-white text-slate-800 placeholder-slate-400 rounded-xl outline-none focus:ring-2 focus:ring-violet-300 shadow-inner"
                placeholder={isX ? "粘贴产品链接, 如 https://adgrowth-lab.github.io" : "粘贴独立站链接, 例如 https://espressomod.com"}
                value={ingestUrlInput}
                onChange={e => setIngestUrlInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleIngestUrl(); }}
              />
              <button
                type="button"
                onClick={handleIngestUrl}
                disabled={ingestingUrl || !ingestUrlInput.trim()}
                className="px-4 py-2 text-xs font-bold text-violet-900 bg-white hover:bg-violet-50 active:bg-violet-100 disabled:opacity-60 rounded-xl transition-all shadow-xs flex items-center gap-1.5 flex-shrink-0"
              >
                {ingestingUrl ? <span className="animate-spin text-xs">⏳</span> : <span>✨</span>}
                <span>{ingestingUrl ? 'AI 抓取推演中...' : '一键建仓'}</span>
              </button>
            </div>
          </div>

          {/* Platform Selector */}
          <section className="space-y-2">
            <S>监控平台 (Platform)</S>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => handleSelectPlatform('reddit')}
                className={`flex items-center justify-center gap-1.5 p-2.5 rounded-xl border text-xs font-semibold transition-all ${
                  isReddit
                    ? 'border-orange-500 bg-orange-50 text-orange-600 shadow-xs'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                }`}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z"/></svg>
                Reddit 社区
              </button>
              <button
                type="button"
                onClick={() => handleSelectPlatform('x')}
                className={`flex items-center justify-center gap-1.5 p-2.5 rounded-xl border text-xs font-semibold transition-all ${
                  isX
                    ? 'border-black bg-black text-white shadow-xs'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                }`}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                </svg>
                𝕏 (Twitter)
              </button>
              <button
                type="button"
                onClick={() => handleSelectPlatform('forum')}
                className={`flex items-center justify-center gap-1.5 p-2.5 rounded-xl border text-xs font-semibold transition-all ${
                  isForum
                    ? 'border-emerald-600 bg-emerald-50 text-emerald-700 shadow-xs'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                }`}
              >
                <span className="text-sm">🌐</span>
                垂直技术论坛
              </button>
            </div>
          </section>

          <div className="border-t border-slate-100" />

          {/* Credentials */}
          <section className="space-y-3.5">
            <S>Credentials</S>
            {isForum ? (
              <div className="space-y-3">
                <div className="bg-emerald-50/70 border border-emerald-200/80 rounded-xl p-3.5 flex items-start gap-3">
                  <span className="text-xl">🌐</span>
                  <div>
                    <div className="text-xs font-semibold text-emerald-900">免凭据直连监听模式 (Public RSS / Atom Engine)</div>
                    <p className="text-xs text-emerald-700 mt-1 leading-relaxed">
                      垂直技术论坛（如 vBulletin, phpBB, XenForo）基于 RSS2/Atom 开放流直连监控，无需账号即可实时捕获帖子。
                    </p>
                  </div>
                </div>
                <label className="block">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-600">论坛全自动回帖账号 (Web Session Cookie)</span>
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        setActiveTab('vault');
                      }}
                      className="text-xs text-emerald-700 hover:text-emerald-800 font-semibold underline flex items-center gap-1 cursor-pointer"
                    >
                      🔑 去 Vault 录入/管理 Cookie
                    </button>
                  </div>
                  <select className="inp mt-1.5" value={lst.forum_credential_id || ''} onChange={e => update('forum_credential_id', e.target.value)}>
                    <option value="">未指定账号（使用全局默认论坛凭据 / 辅助秒发）</option>
                    {forumCreds.map(c => <option key={c.id} value={c.id}>{c.name} {c.username ? `(${c.username})` : ''}</option>)}
                  </select>
                  <p className="text-xs text-slate-400 mt-1">在 Vault 中添加论坛账号并填入 Cookie 后，开启全托管即可全自动在后台自动提交回帖。</p>
                </label>
              </div>
            ) : isX ? (
              <label className="block">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-600">𝕏 (Twitter) 账号凭据</span>
                  <span className="text-xs text-emerald-600 font-medium bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100">
                    支持免 API 模式
                  </span>
                </div>
                <select className="inp mt-1.5" value={lst.x_credential_id || ''} onChange={e => update('x_credential_id', e.target.value)}>
                  <option value="">免 API 模式（自动使用公开推文流发现引擎）</option>
                  {xCreds.map(c => <option key={c.id} value={c.id}>{c.name} {c.username ? `(@${c.username})` : ''}</option>)}
                </select>
                <p className="text-xs text-slate-400 mt-1">留空时自动通过免 API 引擎监控推文；如需自动回推，请在 Vault 绑定账号密钥或 Cookie。</p>
              </label>
            ) : (
              <label className="block">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-600">Reddit Account</span>
                  <span className="text-xs text-emerald-600 font-medium bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100">
                    支持免 API 模式
                  </span>
                </div>
                <select className="inp mt-1.5" value={lst.reddit_credential_id || ''} onChange={e => update('reddit_credential_id', e.target.value)}>
                  <option value="">免 API 模式（自动使用公开 RSS 轮询引擎，无需账号）</option>
                  {rCreds.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                <p className="text-xs text-slate-400 mt-1">留空或选择免 API 模式即可绕过 Reddit OAuth 及人机验证限制。</p>
              </label>
            )}
            <label className="block">
              <span className="text-sm font-medium text-slate-600">AI Key <span className="font-normal text-slate-400">(用于自动筛选与软植入回帖)</span></span>
              <select className="inp mt-1.5" value={lst.ai_credential_id || ''} onChange={e => update('ai_credential_id', e.target.value)}>
                <option value="">自动使用全局默认 AI Key</option>
                {aiCreds.map(c => <option key={c.id} value={c.id}>{c.name} ({c.type})</option>)}
              </select>
            </label>
          </section>

          <div className="border-t border-slate-100" />

          {/* Configuration */}
          <section className="space-y-3.5">
            <S>Configuration</S>
            <label className="block">
              <span className="text-sm font-medium text-slate-600">Name</span>
              <input className="inp mt-1.5" value={lst.name} onChange={e => update('name', e.target.value)} />
            </label>
            {isForum ? (
              <label className="block">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-600">论坛 RSS 订阅地址 (Forum RSS2 / Atom Feed URL)</span>
                  <button
                    type="button"
                    onClick={() => update('forum_rss_url', 'https://www.buggiesgonewild.com/external.php?type=RSS2')}
                    className="text-[11px] text-emerald-600 hover:text-emerald-700 font-medium underline cursor-pointer"
                  >
                    填入 Buggies Gone Wild 论坛源
                  </button>
                </div>
                <input
                  className="inp mt-1.5 font-mono text-xs"
                  value={lst.forum_rss_url || ''}
                  placeholder="https://www.buggiesgonewild.com/external.php?type=RSS2"
                  onChange={e => update('forum_rss_url', e.target.value)}
                />
                <p className="text-xs text-slate-400 mt-1">
                  兼容 vBulletin (<code className="bg-slate-100 px-1 rounded text-[11px]">external.php?type=RSS2</code>)、phpBB (<code className="bg-slate-100 px-1 rounded text-[11px]">feed.php</code>)、XenForo (<code className="bg-slate-100 px-1 rounded text-[11px]">index.rss</code>) 等主流垂直论坛。
                </p>
              </label>
            ) : !isX ? (
              <label className="block">
                <span className="text-sm font-medium text-slate-600">Subreddits</span>
                <input className="inp mt-1.5" value={lst.subreddits || 'all'} placeholder="all" onChange={e => update('subreddits', e.target.value)} />
                <p className="text-xs text-slate-400 mt-1">Combine with +: <code className="bg-slate-100 px-1 rounded">SaaS+smallbusiness</code></p>
              </label>
            ) : (
              <label className="block">
                <span className="text-sm font-medium text-slate-600">𝕏 关注范围 / 高级语法 <span className="font-normal text-slate-400">(可选)</span></span>
                <input className="inp mt-1.5" value={lst.subreddits || ''} placeholder="例如: lang:en -is:retweet" onChange={e => update('subreddits', e.target.value)} />
                <p className="text-xs text-slate-400 mt-1">留空将全网按下方配置的关键词实时捕捉相关推文。</p>
              </label>
            )}
            <label className="block">
              <span className="text-sm font-medium text-slate-600">Webhook <span className="font-normal text-slate-400">(Bark / Slack / Custom)</span></span>
              <input className="inp mt-1.5" value={lst.webhook || ''} placeholder="https://api.day.app/your_bark_key" onChange={e => update('webhook', e.target.value)} />
              <p className="text-xs text-slate-400 mt-1">填入 Bark URL（例如 <code className="bg-slate-100 px-1 rounded">https://api.day.app/xxx</code>）可在抓到线索时直接推送，并附带 AI 回复一键复制按钮。</p>
            </label>
          </section>

          <div className="border-t border-slate-100" />

          {/* Site Promotion & Auto-Reply */}
          <section className="space-y-3.5 bg-violet-50/60 border border-violet-100 p-4 rounded-xl">
            <div className="flex items-center justify-between">
              <div>
                <S>站点推广与 AI 自动回复任务</S>
                <p className="text-xs text-slate-500 mt-0.5">捕获线索后，AI 会根据独立站工具与诉求自动撰写自然回帖</p>
              </div>
              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={openAiModal}
                  className="text-xs text-violet-700 hover:text-violet-900 bg-white/80 hover:bg-white border border-violet-200 px-2.5 py-1 rounded-lg font-medium flex items-center gap-1 transition-colors shadow-2xs"
                  title="使用 AI 深度解析该项目并自适应生成推荐配置"
                >
                  <span>🪄</span>
                  <span>AI 解析新产品</span>
                </button>
                <label className="relative inline-flex items-center cursor-pointer flex-shrink-0">
                  <input
                    type="checkbox"
                    checked={lst.auto_reply_enabled !== false}
                    className="sr-only peer"
                    onChange={e => update('auto_reply_enabled', e.target.checked)}
                  />
                  <div className="w-9 h-5 bg-slate-200 rounded-full peer peer-checked:bg-violet-600 transition-colors" />
                  <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4" />
                </label>
              </div>
            </div>

            {lst.auto_reply_enabled !== false && (
              <div className="space-y-3 pt-2">
                <div className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="text-sm font-medium text-slate-700">站点/产品名称</span>
                    <input
                      className="inp mt-1.5 text-sm bg-white"
                      placeholder="例如: Fairway Fort / BoltAI / MyTool"
                      value={lst.site_name || ''}
                      onChange={e => update('site_name', e.target.value)}
                    />
                  </label>
                  <label className="block">
                    <span className="text-sm font-medium text-slate-700">推广工具/页面 URL</span>
                    <input
                      className="inp mt-1.5 text-sm bg-white"
                      placeholder="https://example.com/tools"
                      value={lst.site_url || ''}
                      onChange={e => update('site_url', e.target.value)}
                    />
                  </label>
                </div>

                <label className="block">
                  <span className="text-sm font-medium text-slate-700">站点与工具核心功能简介</span>
                  <input
                    className="inp mt-1.5 text-sm bg-white"
                    placeholder="核心技术功能简介，例如：Free Compliance Guide / Developer Diagnostics"
                    value={lst.site_description || ''}
                    onChange={e => update('site_description', e.target.value)}
                  />
                  <p className="text-xs text-slate-400 mt-1">告诉 AI 这个工具能解决发帖用户的什么问题（如技术诊断、合规指南、参数速查等）。</p>
                </label>

                <label className="block">
                  <span className="text-sm font-medium text-slate-700">推广指令与回复风格要求 (Pitch Instructions)</span>
                  <textarea
                    rows={2}
                    className="inp mt-1.5 text-sm bg-white"
                    placeholder="例如：先客观解答技术问题，并在提到州法规时以热心车主口吻推荐工具站。严禁任何 AI 套话或生硬推销！"
                    value={lst.pitch_instruction || ''}
                    onChange={e => update('pitch_instruction', e.target.value)}
                  />
                </label>

                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                      {isForum ? '🌐 垂直技术论坛水手策略 (Stealth Engine)' : (isX ? '𝕏 (Twitter)' : 'Reddit') + ' 流量转化与防封投放策略 (Conversion Engine)'}
                    </span>
                    <span className="text-[11px] font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      {isForum
                        ? (lst.stealth_mode === 'two_step' ? '🎣 二段钓鱼排查' : lst.stealth_mode === 'direct_link' ? '⚡ BBCode 直链' : '🥷 个人主页无痕水手 (0封号)')
                        : (lst.stealth_mode === 'bio_routing' || lst.stealth_mode === 'profile_only'
                            ? '🥷 个人主页穿透 (Bio模式)'
                            : lst.stealth_mode === 'inbound_dm' || lst.anti_ban_mode === 'inbound_dm'
                            ? '📩 逆向受邀私信 (DM模式)'
                            : lst.anti_ban_mode === 'direct_link'
                            ? '⚡ 直接留落地页 (Link模式)'
                            : lst.anti_ban_mode === 'adaptive'
                            ? '🧠 智能场景自适应 (推荐)'
                            : '🛡️ 品牌搜索占坑 (0外链)')
                      }
                    </span>
                  </div>
                  {isForum ? (
                    <div className="grid grid-cols-3 gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => update('stealth_mode', 'profile_only')}
                        className={`text-xs p-2 rounded-lg border text-left transition-all ${
                          (lst.stealth_mode || 'profile_only') === 'profile_only'
                            ? 'border-emerald-600 bg-emerald-50/70 text-emerald-900 font-medium'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        <div className="font-semibold flex items-center gap-1">🥷 个人主页诱捕 (推荐)</div>
                        <div className="text-[10px] text-slate-500 mt-0.5 leading-tight">正文绝不含裸链，100%硬核诊断，引导查看个人Profile/签名档线路图，0删帖0封禁</div>
                      </button>
                      <button
                        type="button"
                        onClick={() => update('stealth_mode', 'two_step')}
                        className={`text-xs p-2 rounded-lg border text-left transition-all ${
                          lst.stealth_mode === 'two_step'
                            ? 'border-violet-500 bg-violet-50/50 text-violet-900 font-medium'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        <div className="font-semibold flex items-center gap-1">🎣 二段式技术互动</div>
                        <div className="text-[10px] text-slate-500 mt-0.5 leading-tight">回复80%排查逻辑，制造关键分叉点提问，待原作者回复后再推介工具</div>
                      </button>
                      <button
                        type="button"
                        onClick={() => update('stealth_mode', 'direct_link')}
                        className={`text-xs p-2 rounded-lg border text-left transition-all ${
                          lst.stealth_mode === 'direct_link'
                            ? 'border-amber-500 bg-amber-50/50 text-amber-900 font-medium'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        <div className="font-semibold flex items-center gap-1">⚡ 原生 BBCode 直链</div>
                        <div className="text-[10px] text-slate-500 mt-0.5 leading-tight">生成原生 [URL="..."]BBCode[/URL] 语法，适合宽松版块直接导流</div>
                      </button>
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => updateMulti({ stealth_mode: 'bio_routing', anti_ban_mode: 'safe' })}
                        className={`text-xs p-2 rounded-lg border text-left transition-all ${
                          (lst.stealth_mode === 'bio_routing' || lst.stealth_mode === 'profile_only')
                            ? 'border-emerald-600 bg-emerald-50 text-emerald-950 font-medium shadow-sm'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        <div className="font-semibold flex items-center gap-1">🥷 个人主页穿透 (Bio)</div>
                        <div className="text-[10px] text-slate-500 mt-0.5 leading-tight">0外链、100%技术解惑，自然引导主页置顶帖落地页承接，0删帖0封号</div>
                      </button>
                      <button
                        type="button"
                        onClick={() => updateMulti({ stealth_mode: 'inbound_dm', anti_ban_mode: 'inbound_dm' })}
                        className={`text-xs p-2 rounded-lg border text-left transition-all ${
                          (lst.stealth_mode === 'inbound_dm' || lst.anti_ban_mode === 'inbound_dm')
                            ? 'border-purple-600 bg-purple-50 text-purple-950 font-medium shadow-sm'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        <div className="font-semibold flex items-center gap-1">📩 逆向受邀私信 (DM)</div>
                        <div className="text-[10px] text-slate-500 mt-0.5 leading-tight">80%技术干货+20%资产缺口邀私聊，启动1v1攻坚与异议化解，高客单首选</div>
                      </button>
                      <button
                        type="button"
                        onClick={() => updateMulti({ stealth_mode: 'direct_link', anti_ban_mode: 'direct_link' })}
                        className={`text-xs p-2 rounded-lg border text-left transition-all ${
                          (lst.anti_ban_mode === 'direct_link' && lst.stealth_mode !== 'inbound_dm' && lst.stealth_mode !== 'bio_routing' && lst.stealth_mode !== 'profile_only')
                            ? 'border-amber-600 bg-amber-50 text-amber-950 font-medium shadow-sm'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        <div className="font-semibold flex items-center gap-1">⚡ 直接留落地页 (Link)</div>
                        <div className="text-[10px] text-slate-500 mt-0.5 leading-tight">文末直接带落地页超链接，仅限求链帖或宽松版块，临门一脚直达</div>
                      </button>
                      <button
                        type="button"
                        onClick={() => updateMulti({ stealth_mode: 'direct_link', anti_ban_mode: 'adaptive' })}
                        className={`text-xs p-2 rounded-lg border text-left transition-all ${
                          (lst.anti_ban_mode === 'adaptive' && lst.stealth_mode !== 'inbound_dm' && lst.stealth_mode !== 'bio_routing' && lst.stealth_mode !== 'profile_only')
                            ? 'border-violet-600 bg-violet-50 text-violet-950 font-medium shadow-sm'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        <div className="font-semibold flex items-center gap-1">🧠 智能动态自适应 (推荐)</div>
                        <div className="text-[10px] text-slate-500 mt-0.5 leading-tight">求链带URL，常规推主页/搜品牌，账号安全与转化动态平衡的最优解</div>
                      </button>
                      <button
                        type="button"
                        onClick={() => updateMulti({ stealth_mode: 'direct_link', anti_ban_mode: 'brand_search' })}
                        className={`text-xs p-2 rounded-lg border text-left transition-all ${
                          ((lst.anti_ban_mode || 'brand_search') === 'brand_search' && lst.stealth_mode !== 'inbound_dm' && lst.stealth_mode !== 'bio_routing' && lst.stealth_mode !== 'profile_only' && lst.anti_ban_mode !== 'adaptive' && lst.anti_ban_mode !== 'direct_link')
                            ? 'border-blue-600 bg-blue-50 text-blue-950 font-medium shadow-sm'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        <div className="font-semibold flex items-center gap-1">🛡️ 品牌搜索占坑 (SEO)</div>
                        <div className="text-[10px] text-slate-500 mt-0.5 leading-tight">0外链0主页，自然植入品牌词引导Google搜索，防𝕏外链算法降权</div>
                      </button>
                    </div>
                  )}
                </div>

                {/* Auto Responder & Throttling */}
                <div className="bg-amber-50/50 border border-amber-200/80 rounded-xl p-3.5 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-bold text-amber-950 flex items-center gap-1.5">
                        <span>🤖 全自动无人值守安全回复与频率节流 (Auto-Submitter & Pacing)</span>
                      </div>
                      <div className="text-[11px] text-amber-800/80 mt-0.5">
                        开启后，AI 回复将自动加入排期队列，严格遵循防封频率阶梯平滑发射。
                      </div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer flex-shrink-0">
                      <input
                        type="checkbox"
                        checked={!!lst.auto_submit_enabled}
                        className="sr-only peer"
                        onChange={e => update('auto_submit_enabled', e.target.checked)}
                      />
                      <div className="w-9 h-5 bg-slate-200 rounded-full peer peer-checked:bg-amber-600 transition-colors" />
                      <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4" />
                    </label>
                  </div>

                  {lst.auto_submit_enabled && (
                    <div className="space-y-4 pt-2 border-t border-amber-200/80">
                      {/* 1. Quick Frequency Preset Pills */}
                      <div>
                        <div className="text-[11px] font-semibold text-slate-700 mb-1.5 flex items-center justify-between">
                          <span>⚡ 一键安全频率预设 (Platform Safety Presets)</span>
                          <span className="text-[10px] text-slate-400 font-normal">点击快速切换防封档位</span>
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                          {presets.map(p => {
                            const active = matchedPreset?.id === p.id;
                            return (
                              <button
                                key={p.id}
                                type="button"
                                onClick={() => applyPreset(p)}
                                className={`p-2.5 rounded-xl border text-left transition-all ${
                                  active
                                    ? 'border-amber-600 bg-white shadow-xs ring-2 ring-amber-400/40'
                                    : 'border-amber-200/60 bg-white/70 hover:bg-white text-slate-700'
                                }`}
                              >
                                <div className="flex items-center justify-between">
                                  <span className="text-xs font-bold text-slate-900">{p.label}</span>
                                  <span className="text-[9px] px-1 py-0.2 rounded bg-amber-100 text-amber-800 font-semibold">{p.tag}</span>
                                </div>
                                <div className="text-[10px] text-slate-500 mt-1 leading-tight font-mono">
                                  {p.cd}m · {p.limit}条/天
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      {/* 2. Interactive Stepper & Quick Pills */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-white/90 p-3 rounded-xl border border-amber-200/70">
                        {/* Cooldown Stepper */}
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-slate-700">两次发帖最小间隔</span>
                            <span className="text-[10px] font-mono font-bold text-amber-800 bg-amber-100 px-1.5 py-0.2 rounded">
                              {currentCd} 分钟
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => stepCooldown(-5)}
                              className="w-8 h-8 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-sm flex items-center justify-center transition-colors"
                            >
                              -
                            </button>
                            <input
                              type="number"
                              min="5"
                              max="240"
                              className="inp text-center text-xs font-mono font-bold py-1.5 bg-white flex-1"
                              value={currentCd}
                              onChange={e => update('reply_cooldown_minutes', parseInt(e.target.value) || (isX ? 45 : 30))}
                            />
                            <button
                              type="button"
                              onClick={() => stepCooldown(5)}
                              className="w-8 h-8 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-sm flex items-center justify-center transition-colors"
                            >
                              +
                            </button>
                          </div>
                          {/* Quick Pills */}
                          <div className="flex items-center gap-1 flex-wrap pt-0.5">
                            {[15, 30, 45, 60, 90].map(m => (
                              <button
                                key={m}
                                type="button"
                                onClick={() => update('reply_cooldown_minutes', m)}
                                className={`text-[10px] font-mono px-1.5 py-0.5 rounded border transition-colors ${
                                  currentCd === m
                                    ? 'bg-amber-600 text-white border-amber-600 font-bold'
                                    : 'bg-white text-slate-600 border-slate-200 hover:border-amber-400'
                                }`}
                              >
                                {m}m
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Daily Limit Stepper */}
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-slate-700">单日回复上限</span>
                            <span className="text-[10px] font-mono font-bold text-amber-800 bg-amber-100 px-1.5 py-0.2 rounded">
                              {currentLimit} 条/天
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => stepLimit(-1)}
                              className="w-8 h-8 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-sm flex items-center justify-center transition-colors"
                            >
                              -
                            </button>
                            <input
                              type="number"
                              min="1"
                              max="50"
                              className="inp text-center text-xs font-mono font-bold py-1.5 bg-white flex-1"
                              value={currentLimit}
                              onChange={e => update('daily_reply_limit', parseInt(e.target.value) || (isX ? 6 : 10))}
                            />
                            <button
                              type="button"
                              onClick={() => stepLimit(1)}
                              className="w-8 h-8 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-sm flex items-center justify-center transition-colors"
                            >
                              +
                            </button>
                          </div>
                          {/* Quick Pills */}
                          <div className="flex items-center gap-1 flex-wrap pt-0.5">
                            {[4, 6, 8, 10, 15, 20].map(cnt => (
                              <button
                                key={cnt}
                                type="button"
                                onClick={() => update('daily_reply_limit', cnt)}
                                className={`text-[10px] font-mono px-1.5 py-0.5 rounded border transition-colors ${
                                  currentLimit === cnt
                                    ? 'bg-amber-600 text-white border-amber-600 font-bold'
                                    : 'bg-white text-slate-600 border-slate-200 hover:border-amber-400'
                                }`}
                              >
                                {cnt}条
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* 3. Real-Time Risk / Pacing Indicator */}
                      <div className={`p-2.5 rounded-xl border text-xs flex items-start gap-2 ${
                        isX && (currentCd < 30 || currentLimit > 12)
                          ? 'bg-rose-50 border-rose-200 text-rose-800'
                          : (!isX && (currentCd < 20 || currentLimit > 15))
                          ? 'bg-amber-100 border-amber-300 text-amber-900'
                          : 'bg-emerald-50 border-emerald-200 text-emerald-800'
                      }`}>
                        <span className="text-base leading-none">
                          {isX && (currentCd < 30 || currentLimit > 12) ? '⚠️' : (!isX && (currentCd < 20 || currentLimit > 15)) ? '⚡' : '🛡️'}
                        </span>
                        <div className="space-y-0.5 leading-snug">
                          <div className="font-semibold text-[11px]">
                            {isX && (currentCd < 30 || currentLimit > 12)
                              ? '频率过高风控警示'
                              : (!isX && (currentCd < 20 || currentLimit > 15))
                              ? '高频互动模式'
                              : '防封评级：极高安全度 (Safe)'}
                          </div>
                          <div className="text-[10px] opacity-90">
                            {isX && (currentCd < 30 || currentLimit > 12)
                              ? '𝕏 平台发帖间隔低于 30m 或每日 >12 条极易被算法识别为 Bot 触发 Shadowban，强烈建议调至 ≥45m 稳健档位。'
                              : (!isX && (currentCd < 20 || currentLimit > 15))
                              ? '当前频率偏高，适合老号或高权重账号，新号建议开启安全养号档位。'
                              : `全天预计每 ${Math.round(24 / currentLimit * 10) / 10} 小时分配 1 次互动，每次提交后强制锁冷 ${currentCd} 分钟，模拟真实真人作息。`}
                          </div>
                        </div>
                      </div>

                      {/* 4. Schedule Window inside Timing Panel */}
                      <div className="bg-white/80 border border-amber-200/80 rounded-xl p-3 space-y-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                              <span>🕒 运行时间窗口与活跃时段 (Active Schedule Window)</span>
                            </div>
                            <div className="text-[10px] text-slate-500 mt-0.5">
                              限制机器人仅在目标用户活跃的白天或工作时间发帖，深夜休眠更拟真。
                            </div>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer flex-shrink-0">
                            <input
                              type="checkbox"
                              checked={!!lst.schedule_enabled}
                              className="sr-only peer"
                              onChange={e => update('schedule_enabled', e.target.checked)}
                            />
                            <div className="w-8 h-4.5 bg-slate-200 rounded-full peer peer-checked:bg-blue-600 transition-colors" />
                            <div className="absolute top-0.5 left-0.5 w-3.5 h-3.5 bg-white rounded-full shadow transition-transform peer-checked:translate-x-3.5" />
                          </label>
                        </div>

                        {lst.schedule_enabled && (
                          <div className="space-y-3 pt-1 border-t border-slate-100 text-xs">
                            {/* Timezone with Quick Pills */}
                            <div>
                              <div className="flex items-center justify-between mb-1">
                                <span className="font-medium text-slate-700">时区设置 (Timezone)</span>
                                <span className="text-[10px] font-mono text-slate-400">{lst.schedule_timezone || 'UTC'}</span>
                              </div>
                              <div className="flex gap-1.5 flex-wrap mb-1.5">
                                {[
                                  ['America/New_York', '美东 EDT'],
                                  ['America/Los_Angeles', '美西 PDT'],
                                  ['Europe/London', '欧洲 CET'],
                                  ['Asia/Shanghai', '北京 CST'],
                                  ['UTC', 'UTC'],
                                ].map(([tz, label]) => (
                                  <button
                                    key={tz}
                                    type="button"
                                    onClick={() => update('schedule_timezone', tz)}
                                    className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                                      (lst.schedule_timezone || 'UTC') === tz
                                        ? 'bg-blue-600 text-white border-blue-600 font-bold'
                                        : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                                    }`}
                                  >
                                    {label}
                                  </button>
                                ))}
                              </div>
                              <input
                                className="inp text-xs font-mono bg-white"
                                value={lst.schedule_timezone || 'UTC'}
                                placeholder="例如: America/New_York"
                                onChange={e => update('schedule_timezone', e.target.value)}
                              />
                            </div>

                            {/* Active Days */}
                            <div>
                              <span className="font-medium text-slate-700 block mb-1">活跃日期 (Active Days)</span>
                              <div className="flex gap-1 flex-wrap">
                                {DAYS.map(([label, n]) => {
                                  const days = Array.isArray(lst.schedule_days) ? lst.schedule_days : [0, 1, 2, 3, 4, 5, 6];
                                  const on = days.includes(n);
                                  return (
                                    <button
                                      key={n}
                                      type="button"
                                      onClick={() => toggleDay(n)}
                                      className={`text-[10px] px-2.5 py-1 rounded-lg border font-medium transition-all ${
                                        on ? 'bg-slate-900 text-white border-slate-900 font-bold' : 'bg-white text-slate-500 border-slate-200 hover:border-slate-400'
                                      }`}
                                    >
                                      {label}
                                    </button>
                                  );
                                })}
                              </div>
                            </div>

                            {/* Active Hours */}
                            <div className="grid grid-cols-2 gap-3">
                              <label className="block">
                                <span className="text-[11px] font-medium text-slate-600">每日开始时间 (小时 0-23)</span>
                                <input
                                  type="number"
                                  min="0"
                                  max="23"
                                  className="inp mt-1 text-xs bg-white"
                                  value={lst.schedule_start ?? 8}
                                  onChange={e => update('schedule_start', +e.target.value)}
                                />
                              </label>
                              <label className="block">
                                <span className="text-[11px] font-medium text-slate-600">每日结束时间 (小时 1-24)</span>
                                <input
                                  type="number"
                                  min="1"
                                  max="24"
                                  className="inp mt-1 text-xs bg-white"
                                  value={lst.schedule_end ?? 22}
                                  onChange={e => update('schedule_end', +e.target.value)}
                                />
                              </label>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Dark Fleet Autonomous Closed-Loop */}
                <div className="bg-purple-50/60 border border-purple-200/80 rounded-xl p-3.5 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-semibold text-purple-950 flex items-center gap-1.5">
                        <span>🛸 Dark Fleet 无人值守全自动巡航 (Autonomous Closed-Loop Dispatch)</span>
                      </div>
                      <div className="text-[11px] text-purple-700 mt-0.5">
                        命中高价值线索（Tier 1/2）且安全预审通过时，无需人工点击即可全自动排期发射。
                      </div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer flex-shrink-0">
                      <input
                        type="checkbox"
                        checked={lst.dark_fleet_enabled !== false}
                        className="sr-only peer"
                        onChange={e => update('dark_fleet_enabled', e.target.checked)}
                      />
                      <div className="w-9 h-5 bg-slate-200 rounded-full peer peer-checked:bg-purple-600 transition-colors" />
                      <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4" />
                    </label>
                  </div>

                  {lst.dark_fleet_enabled !== false && (
                    <div className="grid grid-cols-2 gap-3 pt-1 border-t border-purple-100 text-xs">
                      <label className="block">
                        <span className="text-xs font-medium text-slate-700">自动发射最低意向分</span>
                        <input
                          type="number"
                          min="50"
                          max="95"
                          className="inp mt-1 text-xs bg-white"
                          value={lst.dark_fleet_min_opp ?? 70}
                          onChange={e => update('dark_fleet_min_opp', parseInt(e.target.value) || 70)}
                        />
                        <span className="text-[10px] text-slate-400">建议 ≥70 分 (高意图线索才自动发射)</span>
                      </label>
                      <label className="block">
                        <span className="text-xs font-medium text-slate-700">AI 预审员最低安全分</span>
                        <input
                          type="number"
                          min="6"
                          max="10"
                          className="inp mt-1 text-xs bg-white"
                          value={lst.dark_fleet_min_safety ? (lst.dark_fleet_min_safety > 10 ? Math.round(lst.dark_fleet_min_safety / 10) : lst.dark_fleet_min_safety) : 8}
                          onChange={e => update('dark_fleet_min_safety', parseInt(e.target.value) || 8)}
                        />
                        <span className="text-[10px] text-slate-400">建议 ≥8 分 (安全结论必须为 PASSED)</span>
                      </label>
                    </div>
                  )}
                </div>

                {/* Domain Metapersona / 赛道专属 AI 人设矩阵 */}
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 space-y-3">
                  <div className="flex items-center justify-between flex-wrap gap-2 cursor-pointer select-none" onClick={() => toggleSection('personas')}>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400 font-mono">
                        {collapsedSections.personas ? '▶' : '▼'}
                      </span>
                      <div>
                        <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                          <span>🎭 赛道专属 AI 人设矩阵 (Domain Metapersonas)</span>
                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700">
                            {(lst.personas || []).length} 个专家人设
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          针对任何新赛道（咖啡机、SaaS、露营、独立站等）一键推演立体专家角色，AI 回复根据技术痛点智能自适应路由。
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 flex-wrap" onClick={e => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={handleLoadDefaultGolfPersonas}
                        className="px-2 py-1 text-[11px] font-medium text-slate-600 bg-white hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
                        title="恢复 4 大高尔夫球车经典人设预设"
                      >
                        ↺ 经典预设
                      </button>
                      <button
                        type="button"
                        onClick={handleAiGeneratePersonas}
                        disabled={generatingPersonas}
                        className="px-2.5 py-1 text-xs font-semibold text-white bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 rounded-lg transition-all shadow-xs flex items-center gap-1 cursor-pointer disabled:opacity-60"
                        title="根据上方产品名称与功能简介一键智能推演"
                      >
                        {generatingPersonas ? <span className="spin">⏳</span> : '✨'}
                        <span>{generatingPersonas ? '推演中...' : 'AI 推演人设'}</span>
                      </button>
                      <button
                        type="button"
                        onClick={handleOpenAddPersona}
                        className="px-2 py-1 text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition-colors flex items-center gap-1 cursor-pointer"
                      >
                        <span>+</span>
                      </button>
                    </div>
                  </div>

                  {!collapsedSections.personas && (
                    <div className="space-y-2 pt-2 border-t border-slate-200/70">
                      {(!lst.personas || lst.personas.length === 0) ? (
                        <div className="text-center py-5 bg-white border border-dashed border-slate-200 rounded-xl space-y-2">
                          <div className="text-2xl">🎭</div>
                          <div className="text-xs text-slate-600 font-medium">当前未配置赛道专属人设</div>
                          <div className="text-[11px] text-slate-400 max-w-sm mx-auto">
                            换新项目时，只需在上方填写产品名称与简介，点击「一键 AI 推演 4 大人设」，大模型将自动生成立体的技术专家、发烧友与评测顾问角色！
                          </div>
                          <button
                            type="button"
                            onClick={handleAiGeneratePersonas}
                            disabled={generatingPersonas}
                            className="mt-1 px-3 py-1.5 text-xs font-semibold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg border border-indigo-200 transition-colors inline-flex items-center gap-1"
                          >
                            ✨ 为当前项目一键生成专属人设
                          </button>
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                          {lst.personas.map((persona, idx) => (
                            <div key={persona.key || idx} className="bg-white border border-slate-200 hover:border-slate-300 rounded-xl p-3 space-y-2 transition-all">
                              <div className="flex items-start justify-between gap-1">
                                <div>
                                  <div className="text-xs font-bold text-slate-900 flex items-center gap-1">
                                    <span>{persona.label}</span>
                                    <span className="text-[10px] font-mono font-normal text-slate-400">({persona.key})</span>
                                  </div>
                                  <div className="text-[11px] font-medium text-indigo-600 mt-0.5 line-clamp-1">
                                    {persona.name}
                                  </div>
                                </div>
                                <div className="flex items-center gap-1 flex-shrink-0">
                                  <button
                                    type="button"
                                    onClick={() => handleEditPersona(idx)}
                                    className="px-1.5 py-0.5 text-[10px] text-slate-600 hover:bg-slate-100 rounded border border-slate-200"
                                  >
                                    编辑
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleDeletePersona(idx)}
                                    className="px-1.5 py-0.5 text-[10px] text-rose-600 hover:bg-rose-50 rounded border border-rose-200"
                                  >
                                    删除
                                  </button>
                                </div>
                              </div>

                              <div className="text-[11px] text-slate-600 leading-relaxed bg-slate-50 p-2 rounded-lg line-clamp-2">
                                {persona.tone}
                              </div>

                              {persona.match_keywords && persona.match_keywords.length > 0 && (
                                <div className="flex flex-wrap gap-1 pt-1">
                                  {persona.match_keywords.slice(0, 6).map((kw, kidx) => (
                                    <span key={kidx} className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 border border-slate-200">
                                      {kw}
                                    </span>
                                  ))}
                                  {persona.match_keywords.length > 6 && (
                                    <span className="text-[10px] text-slate-400 px-1">
                                      +{persona.match_keywords.length - 6}
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Visual Asset Library / 视觉图表与外链资产库 */}
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 space-y-3">
                  <div className="flex items-center justify-between flex-wrap gap-2 cursor-pointer select-none" onClick={() => toggleSection('assets')}>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400 font-mono">
                        {collapsedSections.assets ? '▶' : '▼'}
                      </span>
                      <div>
                        <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                          <span>🖼️ 视觉资产与图表引流库 (Visual Asset Library)</span>
                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                            {(lst.visual_assets || []).length} 个资产
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          为论坛输出 BBCode 图片包裹外链([URL][IMG][/URL])，并为 Reddit 提供图文长评与学术引用。
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 flex-wrap" onClick={e => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={handleGenerateVisualAssets}
                        disabled={generatingAssets}
                        className="px-2.5 py-1 text-xs font-semibold text-emerald-800 bg-emerald-100 hover:bg-emerald-200 rounded-lg border border-emerald-300 transition-colors flex items-center gap-1 disabled:opacity-50"
                        title="根据站点名称与功能简介，由 AI 自动推演专业技术图表资产"
                      >
                        {generatingAssets ? (
                          <>
                            <span className="animate-spin inline-block">⏳</span>
                            <span>规划中...</span>
                          </>
                        ) : (
                          <>
                            <span>🪄 AI 规划资产</span>
                          </>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={handleLoadDefaultAssets}
                        className="px-2 py-1 text-[11px] font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg border border-indigo-200 transition-colors"
                        title="载入高尔夫球车 7 大技术图表资产预设"
                      >
                        ✨ 球车预设
                      </button>
                      <button
                        type="button"
                        onClick={handleOpenAddAsset}
                        className="px-2 py-1 text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition-colors flex items-center gap-1"
                      >
                        <span>+</span>
                      </button>
                    </div>
                  </div>

                  {!collapsedSections.assets && (
                    <div className="space-y-2 pt-2 border-t border-slate-200/70">
                      {(!lst.visual_assets || lst.visual_assets.length === 0) ? (
                        <div className="text-center py-5 bg-white border border-dashed border-slate-200 rounded-lg px-4">
                          <div className="text-xs text-slate-500 font-medium">暂无图表资产。配置后 AI 将在 Reddit/论坛生成回复时智能匹配并学术引用插入图片！</div>
                          <div className="mt-3 flex items-center justify-center gap-3">
                            <button
                              type="button"
                              onClick={handleGenerateVisualAssets}
                              disabled={generatingAssets}
                              className="px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-lg transition-colors shadow-xs flex items-center gap-1"
                            >
                              <span>🪄</span> {generatingAssets ? '正在推演规划中...' : `为 ${lst.site_name || '当前项目'} 一键推演技术图表`}
                            </button>
                            <button
                              type="button"
                              onClick={handleLoadDefaultAssets}
                              className="text-xs text-slate-400 hover:text-indigo-600 underline"
                            >
                              或加载球车 7 大预设
                            </button>
                          </div>
                        </div>
                      ) : (
                        lst.visual_assets.map((asset, idx) => (
                          <div
                            key={asset.id || idx}
                            className="bg-white border border-slate-200 rounded-lg p-2.5 flex items-start gap-3 hover:border-slate-300 transition-all shadow-xs"
                          >
                            {/* Image preview / icon */}
                            <div className="w-14 h-14 rounded-md border border-slate-100 bg-slate-100 overflow-hidden flex-shrink-0 flex items-center justify-center relative group">
                              {asset.image_url ? (
                                <img
                                  src={asset.image_url}
                                  alt={asset.name}
                                  className="w-full h-full object-cover"
                                  onError={(e) => { e.target.style.display = 'none'; if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex'; }}
                                />
                              ) : null}
                              <div className="w-full h-full hidden items-center justify-center text-xs text-slate-400 bg-slate-50 font-mono">
                                📊
                              </div>
                            </div>

                            {/* Content */}
                            <div className="flex-1 min-w-0 space-y-1">
                              <div className="flex items-center justify-between">
                                <h4 className="text-xs font-semibold text-slate-800 truncate">{asset.name}</h4>
                                <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                                  <button
                                    type="button"
                                    onClick={() => handleEditAsset(idx)}
                                    className="text-[11px] text-slate-500 hover:text-slate-800 px-1.5 py-0.5 rounded hover:bg-slate-100"
                                  >
                                    编辑
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleDeleteAsset(idx)}
                                    className="text-[11px] text-red-500 hover:text-red-700 px-1.5 py-0.5 rounded hover:bg-red-50"
                                  >
                                    删除
                                  </button>
                                </div>
                              </div>
                              <div className="text-[11px] text-slate-600 line-clamp-1">
                                {asset.caption || asset.name}
                              </div>
                              <div className="text-[10px] text-slate-400 truncate flex items-center gap-1">
                                <span className="font-semibold text-slate-500">权威出处:</span>
                                <span className="truncate">{asset.citation_source || `${lst.site_name || '权威数据源'} Dataset`}</span>
                              </div>
                              {/* Intent tags */}
                              {asset.intent_keywords && (
                                <div className="flex flex-wrap gap-1 pt-0.5">
                                  {(Array.isArray(asset.intent_keywords)
                                    ? asset.intent_keywords
                                    : String(asset.intent_keywords).split(',')
                                  ).slice(0, 5).map((kw, ki) => (
                                    <span
                                      key={ki}
                                      className="text-[9px] px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 font-mono"
                                    >
                                      #{kw.trim()}
                                    </span>
                                  ))}
                                  {((Array.isArray(asset.intent_keywords) ? asset.intent_keywords.length : 0) > 5) && (
                                    <span className="text-[9px] text-slate-400">
                                      +{asset.intent_keywords.length - 5}
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>

                {/* Offers & Dynamic Tools Matrix / 动态工具与转化 Offer 矩阵 */}
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 space-y-3">
                  <div className="flex items-center justify-between flex-wrap gap-2 cursor-pointer select-none" onClick={() => toggleSection('offers')}>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400 font-mono">
                        {collapsedSections.offers ? '▶' : '▼'}
                      </span>
                      <div>
                        <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                          <span>🎯 落地工具与 Offer 矩阵 (Offers & Dynamic Tools Matrix)</span>
                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800">
                            {(lst.offers_matrix || []).length} 个转化工具
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          社媒 1v1 私信聊单与三轮心智流时，根据线索痛点关键词自适应匹配最精准的子工具/Offer 落地页。
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 flex-wrap" onClick={e => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={handleGenerateOffersMatrix}
                        disabled={generatingOffers}
                        className="px-2.5 py-1 text-xs font-semibold text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 rounded-lg transition-all shadow-xs flex items-center gap-1 cursor-pointer disabled:opacity-60"
                        title="根据上方产品名称与功能简介一键智能推演落地工具矩阵"
                      >
                        {generatingOffers ? <span className="spin">⏳</span> : '🤖'}
                        <span>{generatingOffers ? '推演中...' : 'AI 生成矩阵'}</span>
                      </button>
                      <button
                        type="button"
                        onClick={handleLoadDefaultOffers}
                        className="px-2 py-1 text-[11px] font-medium text-slate-600 bg-white hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors cursor-pointer"
                        title="恢复高尔夫球车 4 大经典工具预设"
                      >
                        ↺ 经典预设
                      </button>
                      <button
                        type="button"
                        onClick={handleOpenAddOffer}
                        className="px-2 py-1 text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition-colors flex items-center gap-1 cursor-pointer"
                      >
                        <span>+</span>
                      </button>
                    </div>
                  </div>

                  {!collapsedSections.offers && (
                    <div className="space-y-2 pt-2 border-t border-slate-200/70">
                      {(!lst.offers_matrix || lst.offers_matrix.length === 0) ? (
                        <div className="text-center py-5 bg-white border border-dashed border-slate-200 rounded-xl space-y-2 px-4">
                          <div className="text-2xl">🎯</div>
                          <div className="text-xs text-slate-600 font-medium">当前未配置落地工具与 Offer 矩阵</div>
                          <div className="text-[11px] text-slate-400 max-w-sm mx-auto">
                            填写站点名称与功能简介后，点击「AI 自动生成工具矩阵」，大模型将自动拆解你的网站并生成 3~5 个精准子工具/算力落地页与触发关键词！
                          </div>
                          <button
                            type="button"
                            onClick={handleGenerateOffersMatrix}
                            disabled={generatingOffers}
                            className="mt-1 px-3 py-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg border border-emerald-200 transition-colors inline-flex items-center gap-1 cursor-pointer"
                          >
                            🤖 为当前项目一键生成工具矩阵
                          </button>
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                          {lst.offers_matrix.map((offer, idx) => (
                            <div key={offer.key || idx} className="bg-white border border-slate-200 hover:border-slate-300 rounded-xl p-3 space-y-2 transition-all">
                              <div className="flex items-start justify-between gap-1">
                                <div>
                                  <div className="text-xs font-bold text-slate-900 flex items-center gap-1">
                                    <span>{offer.name}</span>
                                    <span className="text-[10px] font-mono font-normal text-slate-400">({offer.key})</span>
                                  </div>
                                  <div className="text-[10px] font-mono text-indigo-600 mt-0.5 line-clamp-1 truncate max-w-[240px]">
                                    🔗 {offer.url}
                                  </div>
                                </div>
                                <div className="flex items-center gap-1 flex-shrink-0">
                                  <button
                                    type="button"
                                    onClick={() => handleEditOffer(idx)}
                                    className="px-1.5 py-0.5 text-[10px] text-slate-600 hover:bg-slate-100 rounded border border-slate-200 cursor-pointer"
                                  >
                                    编辑
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleDeleteOffer(idx)}
                                    className="px-1.5 py-0.5 text-[10px] text-rose-600 hover:bg-rose-50 rounded border border-rose-200 cursor-pointer"
                                  >
                                    删除
                                  </button>
                                </div>
                              </div>

                              {offer.keywords && offer.keywords.length > 0 && (
                                <div className="flex flex-wrap gap-1 pt-0.5">
                                  {(Array.isArray(offer.keywords) ? offer.keywords : String(offer.keywords).split(',')).slice(0, 6).map((kw, kidx) => (
                                    <span key={kidx} className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 border border-slate-200">
                                      {kw.trim()}
                                    </span>
                                  ))}
                                  {((Array.isArray(offer.keywords) ? offer.keywords.length : 0) > 6) && (
                                    <span className="text-[10px] text-slate-400 px-1">
                                      +{offer.keywords.length - 6}
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>

          <div className="border-t border-slate-100" />

          {/* Keywords */}
          <section className="space-y-3">
            <S>Keywords <span className="font-normal normal-case">(Python regex)</span></S>
            <div className="space-y-2">
              {(lst.keywords || []).length === 0
                ? <div className="text-slate-400 text-sm py-2 text-center">No keywords yet.</div>
                : (lst.keywords || []).map((kw, i) => (
                  <div key={i} className="flex items-center gap-2.5 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
                    <span className="font-mono text-sm text-emerald-700 flex-1 truncate">{kw}</span>
                    <button onClick={() => removeKw(i)} className="w-5 h-5 flex items-center justify-center rounded hover:bg-red-100 text-slate-300 hover:text-red-400">×</button>
                  </div>
                ))
              }
            </div>
            <div className="flex gap-2">
              <input
                className="inp font-mono flex-1 text-sm"
                placeholder="e.g. work\Worders?"
                value={kwInput}
                onChange={e => setKwInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addKw()}
              />
              <button onClick={addKw} className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-sm font-medium">Add</button>
            </div>
            <p className="text-xs text-slate-400">⚠ Restart listener after changing keywords.</p>
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
              <div className="text-xs font-semibold text-slate-500">Pattern tester</div>
              <textarea
                rows={2}
                className="inp text-sm bg-white"
                placeholder="Paste sample text here to test all patterns above…"
                value={regexSample}
                onChange={e => setRegexSample(e.target.value)}
              />
              <div className="text-xs leading-relaxed">{testRegex()}</div>
            </div>
          </section>

          <div className="border-t border-slate-100" />

          {/* Notifications */}
          <section className="space-y-3">
            <div className="flex items-center justify-between cursor-pointer select-none" onClick={() => toggleSection('notifications')}>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-slate-400 font-mono">{collapsedSections.notifications ? '▶' : '▼'}</span>
                <S>Webhook 告警通知 <span className="font-normal normal-case text-slate-400">(Slack / Telegram)</span></S>
              </div>
              <span className="text-[10px] text-slate-400">
                {lst.slack_webhook || lst.telegram_bot_token ? '🔔 已配置' : '可选配置'}
              </span>
            </div>
            {!collapsedSections.notifications && (
              <div className="space-y-3 pt-1">
                <label className="block">
                  <span className="text-sm font-medium text-slate-600">Slack Webhook <span className="text-xs font-normal text-slate-400 ml-1">Block Kit format</span></span>
                  <input className="inp mt-1.5 text-sm" value={lst.slack_webhook || ''} placeholder="https://hooks.slack.com/services/…" onChange={e => update('slack_webhook', e.target.value)} />
                  <span className="text-xs text-slate-400 mt-1 block">Get at <a href="https://api.slack.com/messaging/webhooks" target="_blank" rel="noopener" className="text-blue-500 hover:underline">api.slack.com/messaging/webhooks</a></span>
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="text-sm font-medium text-slate-600">Telegram Bot Token</span>
                    <input className="inp mt-1.5 text-sm font-mono" type="password" value={lst.telegram_bot_token || ''} placeholder="123456:ABC…" onChange={e => update('telegram_bot_token', e.target.value)} />
                  </label>
                  <label className="block">
                    <span className="text-sm font-medium text-slate-600">Telegram Chat ID</span>
                    <input className="inp mt-1.5 text-sm font-mono" value={lst.telegram_chat_id || ''} placeholder="-100123…" onChange={e => update('telegram_chat_id', e.target.value)} />
                  </label>
                </div>
                <p className="text-xs text-slate-400">
                  Bot via <a href="https://t.me/BotFather" target="_blank" rel="noopener" className="text-blue-500 hover:underline">@BotFather</a> · Chat ID via <a href="https://t.me/userinfobot" target="_blank" rel="noopener" className="text-blue-500 hover:underline">@userinfobot</a>
                </p>
              </div>
            )}
          </section>

          <div className="border-t border-slate-100" />

          {/* Negative keywords */}
          <section className="space-y-3">
            <S>Negative Keywords <span className="font-normal normal-case">(drop hit if any match)</span></S>
            <div className="space-y-2">
              {(lst.negative_keywords || []).length === 0
                ? <div className="text-slate-400 text-sm py-1">None — all keyword matches pass through.</div>
                : (lst.negative_keywords || []).map((kw, i) => (
                  <div key={i} className="flex items-center gap-2.5 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
                    <span className="font-mono text-sm text-red-600 flex-1 truncate">{kw}</span>
                    <button onClick={() => removeNkw(i)} className="w-5 h-5 flex items-center justify-center rounded hover:bg-red-100 text-red-300 hover:text-red-500">×</button>
                  </div>
                ))
              }
            </div>
            <div className="flex gap-2">
              <input
                className="inp font-mono flex-1 text-sm"
                placeholder="e.g. hate|terrible|not looking"
                value={nkwInput}
                onChange={e => setNkwInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addNkw()}
              />
              <button onClick={addNkw} className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-medium">Add</button>
            </div>
          </section>

          <div className="border-t border-slate-100" />

          {/* Author quality */}
          <section className="space-y-3">
            <S>Author Quality Filter</S>
            <p className="text-xs text-slate-400">Skip posts from brand-new or low-karma accounts. Set to 0 to disable.</p>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-sm font-medium text-slate-600">Min karma</span>
                <input type="number" min="0" className="inp mt-1.5 text-sm" value={lst.min_karma || 0} onChange={e => update('min_karma', +e.target.value)} />
              </label>
              <label className="block">
                <span className="text-sm font-medium text-slate-600">Min account age (days)</span>
                <input type="number" min="0" className="inp mt-1.5 text-sm" value={lst.min_account_age_days || 0} onChange={e => update('min_account_age_days', +e.target.value)} />
              </label>
            </div>
          </section>

          <div className="border-t border-slate-100" />

          {/* AI filter pipeline */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <S>AI Filter Pipeline</S>
              <button
                onClick={addFilter}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-violet-100 hover:bg-violet-200 text-violet-700 font-medium"
              >
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg>
                Add Step
              </button>
            </div>
            {(lst.filters || []).length === 0 && (
              <div className="text-slate-400 text-sm py-1">No filter steps yet. Each hit can be evaluated by Claude before being marked passed/rejected.</div>
            )}
            <div className="space-y-3">
              {(lst.filters || []).map((f, i) => (
                <div key={i} className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold bg-white border border-slate-200 text-slate-500 px-2 py-0.5 rounded-md flex-shrink-0">Step {i + 1}</span>
                    <input
                      className="inp text-sm py-1.5 flex-1 bg-white"
                      value={f.name}
                      placeholder="Step name"
                      onChange={e => updateFilter(i, 'name', e.target.value)}
                    />
                    <label className="relative inline-flex items-center cursor-pointer flex-shrink-0">
                      <input type="checkbox" checked={!!f.enabled} className="sr-only peer" onChange={e => updateFilter(i, 'enabled', e.target.checked)} />
                      <div className="w-8 h-4 bg-slate-200 rounded-full peer peer-checked:bg-violet-500 transition-colors" />
                      <div className="absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4" />
                    </label>
                    <button onClick={() => removeFilter(i)} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-red-100 text-slate-300 hover:text-red-400 text-lg leading-none flex-shrink-0">×</button>
                  </div>
                  <textarea
                    rows={3}
                    className="inp text-sm bg-white"
                    placeholder="Prompt. Tell Claude to reply YES to pass or NO to reject."
                    value={f.prompt}
                    onChange={e => updateFilter(i, 'prompt', e.target.value)}
                  />
                </div>
              ))}
            </div>
          </section>

        </div>
      </div>

      {/* AI Profile Generator Modal */}
      {showAiModal && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div
            className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity"
            onClick={() => !aiLoading && setShowAiModal(false)}
          />
          <div className="relative w-full max-w-2xl bg-white rounded-2xl shadow-2xl border border-slate-100 flex flex-col max-h-[90vh] overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white flex-shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-violet-100 text-violet-600 flex items-center justify-center text-base shadow-xs">
                  🪄
                </div>
                <div>
                  <h3 className="font-semibold text-slate-900 text-base">AI 项目监听画像生成器</h3>
                  <p className="text-xs text-slate-500">
                    为 {isX ? '𝕏 (Twitter) 全局公海' : 'Reddit 社区'} 自动挖掘高意向复合词、排他负词与软植入策略
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => !aiLoading && setShowAiModal(false)}
                className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 text-xl leading-none"
              >
                ×
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="text-xs font-semibold text-slate-700">产品 / 品牌名称 <span className="text-red-500">*</span></span>
                    <input
                      className="inp mt-1 text-sm bg-white"
                      placeholder="例如: Fairway Fort / BoltAI / Typefully"
                      value={aiForm.site_name}
                      onChange={e => setAiForm({ ...aiForm, site_name: e.target.value })}
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-semibold text-slate-700">推广工具 / 页面 URL <span className="text-slate-400 font-normal">(可选)</span></span>
                    <input
                      className="inp mt-1 text-sm bg-white"
                      placeholder="https://example.com/tools"
                      value={aiForm.site_url}
                      onChange={e => setAiForm({ ...aiForm, site_url: e.target.value })}
                    />
                  </label>
                </div>

                <label className="block">
                  <span className="text-xs font-semibold text-slate-700">产品核心定位与解决的痛点 <span className="text-red-500">*</span></span>
                  <textarea
                    rows={3}
                    className="inp mt-1 text-sm bg-white"
                    placeholder="详细描述产品是做什么的、核心受众是谁、能帮他们解决什么问题。例如：针对高尔夫球车和低速车(LSV)的全美50州路权合法化查询与VIN码速查工具，提供各州法律合规对比与挡风玻璃/安全带标准查询。"
                    value={aiForm.site_description}
                    onChange={e => setAiForm({ ...aiForm, site_description: e.target.value })}
                  />
                  <p className="text-[11px] text-slate-400 mt-1">
                    AI 将深度拆解该痛点，{isX ? '并组合出「品类主词 × 意向行为」的复合搜索词，防止 𝕏 公海泛词歧义。' : '并匹配最相关的 Reddit 活跃版块与高意图搜索词。'}
                  </p>
                </label>

                <label className="block">
                  <span className="text-xs font-semibold text-slate-700">调用的 AI 凭据</span>
                  <select
                    className="inp mt-1 text-xs bg-white"
                    value={aiForm.credential_id}
                    onChange={e => setAiForm({ ...aiForm, credential_id: e.target.value })}
                  >
                    <option value="">自动使用全局默认 AI Key (Claude / OpenAI)</option>
                    {aiCreds.map(c => (
                      <option key={c.id} value={c.id}>{c.name} ({c.type})</option>
                    ))}
                  </select>
                </label>

                <div className="pt-1">
                  <button
                    type="button"
                    onClick={handleAiGenerate}
                    disabled={aiLoading || !aiForm.site_name.trim() || !aiForm.site_description.trim()}
                    className={`w-full py-2.5 px-4 rounded-xl text-sm font-semibold text-white flex items-center justify-center gap-2 shadow-xs transition-all ${
                      aiLoading || !aiForm.site_name.trim() || !aiForm.site_description.trim()
                        ? 'bg-slate-300 cursor-not-allowed'
                        : 'bg-gradient-to-r from-violet-600 via-indigo-600 to-blue-600 hover:from-violet-700 hover:to-blue-700 active:scale-[0.99]'
                    }`}
                  >
                    {aiLoading ? (
                      <>
                        <span className="spin text-base">⏳</span>
                        <span>AI 正在深度分析受众生态与关键词策略...</span>
                      </>
                    ) : (
                      <>
                        <span>✨</span>
                        <span>立即智能生成监听画像与规则</span>
                      </>
                    )}
                  </button>
                </div>

                {aiError && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600">
                    {aiError}
                  </div>
                )}

                {/* AI Result Preview */}
                {aiResult && (
                  <div className="mt-4 p-4 bg-slate-50 border border-slate-200/80 rounded-xl space-y-3.5 animate-in fade-in duration-200">
                    <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                      <div className="text-xs font-bold text-slate-800 uppercase tracking-wide flex items-center gap-1.5">
                        <span>🎯</span>
                        <span>AI 智能生成方案预览</span>
                      </div>
                      <span className="text-[11px] font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                        生成完成
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div>
                        <span className="text-slate-400 block font-medium">推荐监听器名称</span>
                        <span className="text-slate-800 font-semibold mt-0.5 block">{aiResult.name}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 block font-medium">{isX ? '𝕏 关注范围' : '推荐 Subreddits'}</span>
                        <span className="text-slate-800 font-mono mt-0.5 block truncate">
                          {aiResult.subreddits || (isX ? '全网实时公海' : 'all')}
                        </span>
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-semibold text-slate-700">高意图监控关键词 ({(aiResult.keywords || []).length} 组)</span>
                        {isX && <span className="text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">已自动完成复合锚定，杜绝歧义</span>}
                      </div>
                      <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto p-2 bg-white rounded-lg border border-slate-200">
                        {(aiResult.keywords || []).map((k, i) => (
                          <span key={i} className="text-[11px] font-mono bg-emerald-50 text-emerald-800 border border-emerald-200 px-2 py-0.5 rounded-md">
                            {k}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div>
                      <span className="text-xs font-semibold text-slate-700 block mb-1.5">负向排除词 ({(aiResult.negative_keywords || []).length} 组)</span>
                      <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto p-2 bg-white rounded-lg border border-slate-200">
                        {(aiResult.negative_keywords || []).map((nk, i) => (
                          <span key={i} className="text-[11px] font-mono bg-red-50 text-red-700 border border-red-200 px-2 py-0.5 rounded-md">
                            {nk}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div>
                      <span className="text-xs font-semibold text-slate-700 block mb-1">AI 二元精准判别 Prompt (Filter Step 1)</span>
                      <div className="text-xs font-mono text-slate-600 bg-white p-2.5 rounded-lg border border-slate-200 leading-relaxed max-h-24 overflow-y-auto">
                        {aiResult.filter_prompt}
                      </div>
                    </div>

                    <div>
                      <span className="text-xs font-semibold text-slate-700 block mb-1">推广风格与软植入人设 (Pitch Instructions)</span>
                      <div className="text-xs text-slate-600 bg-white p-2.5 rounded-lg border border-slate-200 leading-relaxed">
                        {aiResult.pitch_instruction}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3.5 border-t border-slate-100 bg-slate-50 flex items-center justify-between flex-shrink-0">
              <button
                type="button"
                onClick={() => !aiLoading && setShowAiModal(false)}
                className="px-4 py-2 rounded-xl text-xs font-medium text-slate-600 hover:bg-slate-200/60 transition-colors"
              >
                取消
              </button>
              {aiResult && (
                <button
                  type="button"
                  onClick={handleApplyProfile}
                  className="px-5 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm flex items-center gap-1.5 transition-all"
                >
                  <span>✨</span>
                  <span>一键应用到当前监听器</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Visual Asset Edit/Add Modal */}
      {showAssetModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-semibold text-slate-800 flex items-center gap-2">
                <span>📊</span> {editingAssetIndex >= 0 ? '编辑图表资产' : '添加视觉图表资产'}
              </h3>
              <button
                type="button"
                onClick={() => setShowAssetModal(false)}
                className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 text-lg"
              >
                ×
              </button>
            </div>

            <div className="space-y-3">
              <label className="block">
                <span className="text-xs font-semibold text-slate-700">资产名称 <span className="text-red-500">*</span></span>
                <input
                  className="inp mt-1 text-sm bg-white"
                  placeholder="例如: 50-State Street-Legal Compliance Matrix"
                  value={assetForm.name}
                  onChange={e => setAssetForm({ ...assetForm, name: e.target.value })}
                />
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-700">高清图片 CDN URL <span className="text-red-500">*</span></span>
                <input
                  className="inp mt-1 text-sm bg-white font-mono"
                  placeholder="https://your-domain.com/cdn/.../chart.webp"
                  value={assetForm.image_url}
                  onChange={e => setAssetForm({ ...assetForm, image_url: e.target.value })}
                />
                <span className="text-[10px] text-slate-400">垂直论坛 BBCode 会将此图片包装为跳转超链接</span>
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-700">点击跳转落地页 (Target URL)</span>
                <input
                  className="inp mt-1 text-sm bg-white font-mono"
                  placeholder="https://your-domain.com/pages/tools"
                  value={assetForm.target_url}
                  onChange={e => setAssetForm({ ...assetForm, target_url: e.target.value })}
                />
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-700">权威学术/数据出处 (Citation Source)</span>
                <input
                  className="inp mt-1 text-sm bg-white"
                  placeholder="例如: Source: NHTSA 49 CFR § 571.500 & State DOT Statutory Frameworks"
                  value={assetForm.citation_source}
                  onChange={e => setAssetForm({ ...assetForm, citation_source: e.target.value })}
                />
                <span className="text-[10px] text-slate-400">高权威出处可直接规避社区推销嫌疑，拉满置顶权重</span>
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-700">图表解说文案 (Caption)</span>
                <input
                  className="inp mt-1 text-sm bg-white"
                  placeholder="例如: Complete 50-State Golf Cart vs. Low-Speed Vehicle Matrix."
                  value={assetForm.caption}
                  onChange={e => setAssetForm({ ...assetForm, caption: e.target.value })}
                />
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-700">意图触发词 (Intent Keywords, 逗号分隔)</span>
                <textarea
                  rows={2}
                  className="inp mt-1 text-sm bg-white"
                  placeholder="state, law, legal, dmv, street, fl, florida, speed, road"
                  value={assetForm.intent_keywords}
                  onChange={e => setAssetForm({ ...assetForm, intent_keywords: e.target.value })}
                />
                <span className="text-[10px] text-slate-400">当原帖命中这些词汇时，AI 会优先自动在回复中调用此图表</span>
              </label>
            </div>

            <div className="pt-2 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowAssetModal(false)}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSaveAsset}
                disabled={!assetForm.name.trim() || !assetForm.image_url.trim()}
                className="px-5 py-2 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 rounded-xl transition-colors shadow-xs"
              >
                保存资产
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Domain Persona Edit/Add Modal */}
      {showPersonaModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-semibold text-slate-800 flex items-center gap-2">
                <span>🎭</span> {editingPersonaIndex >= 0 ? '编辑赛道专家人设' : '添加赛道专家人设'}
              </h3>
              <button
                type="button"
                onClick={() => setShowPersonaModal(false)}
                className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 text-lg"
              >
                ×
              </button>
            </div>

            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-xs font-semibold text-slate-700">Emoji 与角色标签 <span className="text-red-500">*</span></span>
                  <input
                    className="inp mt-1 text-sm bg-white"
                    placeholder="例如: ☕ 萃取调参老饕"
                    value={personaForm.label}
                    onChange={e => setPersonaForm({ ...personaForm, label: e.target.value })}
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-semibold text-slate-700">唯一标识 Key (英文简写)</span>
                  <input
                    className="inp mt-1 text-sm bg-white font-mono"
                    placeholder="例如: barista"
                    value={personaForm.key}
                    onChange={e => setPersonaForm({ ...personaForm, key: e.target.value })}
                  />
                </label>
              </div>

              <label className="block">
                <span className="text-xs font-semibold text-slate-700">英文专业角色全称</span>
                <input
                  className="inp mt-1 text-sm bg-white"
                  placeholder="例如: Senior Specialty Barista & Dialing Guru"
                  value={personaForm.name}
                  onChange={e => setPersonaForm({ ...personaForm, name: e.target.value })}
                />
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-700">口吻指导与诊断视角 (Tone & Diagnosis Guidance) <span className="text-red-500">*</span></span>
                <textarea
                  rows={3}
                  className="inp mt-1 text-sm bg-white"
                  placeholder="指导 AI 在回复时采取的具体说话风格、专业术语深度和解决问题的切入角度..."
                  value={personaForm.tone}
                  onChange={e => setPersonaForm({ ...personaForm, tone: e.target.value })}
                />
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-700">意图匹配关键词 (Match Keywords, 逗号分隔)</span>
                <textarea
                  rows={2}
                  className="inp mt-1 text-sm bg-white font-mono text-xs"
                  placeholder="grind, extraction, sour, bitter, ratio, channelling, wdt"
                  value={personaForm.match_keywords}
                  onChange={e => setPersonaForm({ ...personaForm, match_keywords: e.target.value })}
                />
                <span className="text-[10px] text-slate-400">当原帖包含这些词汇时，系统将自动分配该角色生成专业回复</span>
              </label>
            </div>

            <div className="pt-2 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowPersonaModal(false)}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSavePersona}
                disabled={!personaForm.label.trim() || !personaForm.tone.trim()}
                className="px-5 py-2 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 rounded-xl transition-colors shadow-xs"
              >
                保存人设
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Offer Edit/Add Modal */}
      {showOfferModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-semibold text-slate-800 flex items-center gap-2">
                <span>🎯</span> {editingOfferIndex >= 0 ? '编辑落地工具 / Offer' : '添加落地工具 / Offer'}
              </h3>
              <button
                type="button"
                onClick={() => setShowOfferModal(false)}
                className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 text-lg cursor-pointer"
              >
                ×
              </button>
            </div>

            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-xs font-semibold text-slate-700">工具/Offer 名称 <span className="text-red-500">*</span></span>
                  <input
                    className="inp mt-1 text-sm bg-white"
                    placeholder="例如: 极速与速比在线计算器"
                    value={offerForm.name}
                    onChange={e => setOfferForm({ ...offerForm, name: e.target.value })}
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-semibold text-slate-700">唯一标识 Key (英文简写)</span>
                  <input
                    className="inp mt-1 text-sm bg-white font-mono"
                    placeholder="例如: speed_calc"
                    value={offerForm.key}
                    onChange={e => setOfferForm({ ...offerForm, key: e.target.value })}
                  />
                </label>
              </div>

              <label className="block">
                <span className="text-xs font-semibold text-slate-700">落地目标 URL (完整 URL 或相对路径) <span className="text-red-500">*</span></span>
                <input
                  className="inp mt-1 text-sm bg-white font-mono text-xs"
                  placeholder="https://example.com/tools?tool=calculator 或 /tools/calculator"
                  value={offerForm.url}
                  onChange={e => setOfferForm({ ...offerForm, url: e.target.value })}
                />
                <span className="text-[10px] text-slate-400">当线索命中触发词时，私信与三轮聊单将直达此目标 URL</span>
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-700">意图触发词 (Keywords, 逗号分隔) <span className="text-red-500">*</span></span>
                <textarea
                  rows={3}
                  className="inp mt-1 text-sm bg-white font-mono text-xs"
                  placeholder="speed, mph, fast, speed code, navitas, controller, gear, rpm"
                  value={offerForm.keywords}
                  onChange={e => setOfferForm({ ...offerForm, keywords: e.target.value })}
                />
                <span className="text-[10px] text-slate-400">当潜在客户的发帖或评论中包含这些词汇时，自动匹配并推荐该工具</span>
              </label>
            </div>

            <div className="pt-2 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowOfferModal(false)}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-xl transition-colors cursor-pointer"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSaveOffer}
                disabled={!offerForm.name.trim()}
                className="px-5 py-2 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 rounded-xl transition-colors shadow-xs cursor-pointer"
              >
                保存工具 Offer
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
