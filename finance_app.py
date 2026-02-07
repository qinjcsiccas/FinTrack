import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
from datetime import datetime, timedelta

# --- 页面配置 ---
st.set_page_config(page_title="Jincheng's 财务看板", layout="wide")

# --- 0. 移动端适配 CSS ---
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.5rem !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- 1. 定义占位符与标签页 (Layout) ---
# 技巧：先定义顶部的 KPI 区域（稍后填充），再定义 Tabs
kpi_placeholder = st.container()
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 趋势", "⏱️ 速率", "💰 分类", "🏆 预测", "⚙️ 设置"])

# =========================================================
#  第 5 页：设置 (Settings) - 优先执行，获取全局参数
# =========================================================
with tab5:
    st.header("⚙️ 数据与参数设置")
    
    # 1. 数据源设置
    st.subheader("1. 数据源")
    data_source = None
    
    # 自动获取 URL
    try:
        query_params = st.query_params
    except:
        query_params = st.experimental_get_query_params()
    auto_url = query_params.get("csv_url", None)
    if isinstance(auto_url, list): auto_url = auto_url[0]
    
    if auto_url:
        st.success(f"🔗 已链接云端数据")
        data_source = auto_url
        if st.button("🔄 刷新云端数据", use_container_width=True):
            st.rerun()
    else:
        uploaded_file = st.file_uploader("上传 saving.csv (或从 App 首页绑定链接)", type="csv")
        if uploaded_file:
            data_source = uploaded_file

    st.divider()

    # 2. 里程碑设置
    st.subheader("2. 职业/生活里程碑")
    default_milestones = pd.DataFrame([
        {"日期": datetime(2023, 6, 14).date(), "名称": "公司A"}
    ])
    ms_df = st.data_editor(
        default_milestones,
        num_rows="dynamic",
        column_config={
            "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD", required=True),
            "名称": st.column_config.TextColumn("阶段名称", required=True)
        },
        hide_index=True,
        use_container_width=True,
        key="milestone_editor"
    )
    
    milestones = []
    if ms_df is not None and not ms_df.empty:
        valid_df = ms_df.dropna(subset=['日期', '名称'])
        for _, row in valid_df.iterrows():
            milestones.append({
                "date": pd.to_datetime(row['日期']), 
                "label": str(row['名称']).strip()
            })
    milestones = sorted(milestones, key=lambda x: x['date'])

    st.divider()

    # 3. 目标与隐私 (使用列布局优化空间)
    st.subheader("3. 目标与显示")
    c_set1, c_set2 = st.columns(2)
    with c_set1:
        sd_input = st.date_input("记账起始日", datetime(2023, 2, 25))
        target_goal = st.number_input("目标金额 (元)", value=1000000, step=100000)
    with c_set2:
        velocity_step = st.number_input("进阶步长 (元)", value=100000, step=10000)
        privacy_mode = st.toggle("👁️ 隐私模式 (隐藏金额)", value=False)

    # 整理参数
    start_dt = pd.Timestamp(sd_input)
    job_start_dt = milestones[0]['date'] if milestones else pd.Timestamp(datetime(2023, 6, 14))


# --- 辅助函数 (依赖 privacy_mode) ---
def fmt_money(val, is_kpi=False):
    if privacy_mode: return "****"
    if is_kpi: return f"¥{val:,.0f}"
    return val

def mask_fig(fig, axis='y'):
    # 移动端图表布局优化
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    if privacy_mode:
        if axis == 'y': fig.update_yaxes(showticklabels=False, title_text="****")
        elif axis == 'x': fig.update_xaxes(showticklabels=False, title_text="****")
        fig.update_traces(hovertemplate="%{x}<br>****") 
        fig.update_traces(texttemplate="")
    return fig

# --- 数据处理逻辑 ---
@st.cache_data(ttl=1)
def load_and_process_data(file, start_date_val):
    df = pd.read_csv(file)
    base_date = pd.Timestamp(start_date_val)
    df['Date'] = df['Day'].apply(lambda x: base_date + timedelta(days=float(x)))
    
    df['Bank'] = df['Bank'].fillna(0).astype(float)
    df['Invest'] = df['Invest'].fillna(0).astype(float)
    df['Total_Assets'] = df['Bank'] + df['Invest']
    df['Change'] = df['Total_Assets'].diff().fillna(0)
    df['Notes'] = df['Notes'].fillna('').astype(str)
    
    def adaptive_tagging(row):
        note = str(row['Notes']).strip()
        change = row['Change']
        if change == 0 and not note: return '无变动'
        import re
        segments = re.split('[;；]', note)
        valid_cats = []
        for s in segments:
            parts = re.split('[:：]', s)
            cat = parts[0].strip()
            if cat and cat not in ['里程碑', '备注', '备忘', '2025', '2026']:
                valid_cats.append(cat)
        if any(k in note for k in ['理财', '买入', '基金', '转入']) and abs(change) < 10:
            return '资产转移'
        res_tag = valid_cats[0] if valid_cats else "其他"
        prefix = "📈" if change > 0 else "💸"
        return f"{prefix}{res_tag}"

    df['Tag'] = df.apply(adaptive_tagging, axis=1)
    
    def assign_stage_dynamic(d):
        current_label = "初始阶段"
        stage_start_date = milestones[0]['date'] if milestones else d
        for m in milestones:
            if d >= m['date']:
                current_label = m['label']
                stage_start_date = m['date']
            else:
                break
        years_passed = (d - stage_start_date).days // 365
        return f"{current_label} (第{years_passed + 1}年)"
    
    df['Stage'] = df['Date'].apply(assign_stage_dynamic)
    
    df_res = df.set_index('Date')['Total_Assets'].resample('M').last()
    monthly_diff = df_res.diff().fillna(0)
    
    season_df = pd.DataFrame({'Net_Change': monthly_diff})
    season_df['Year'] = season_df.index.year
    season_df['Month'] = season_df.index.month
    season_pivot = season_df.pivot(index='Year', columns='Month', values='Net_Change')
    
    df['资产类型:银行'] = df['Bank']
    df['资产类型:投资'] = df['Invest']
    return df, monthly_diff, season_pivot

def calculate_milestone_velocity(df, step):
    milestones_res = []
    start_val = df['Total_Assets'].min()
    current_target = (start_val // step + 1) * step
    last_date = df['Date'].iloc[0]
    sorted_df = df.sort_values('Date')
    
    while current_target <= df['Total_Assets'].max():
        reach_row = sorted_df[sorted_df['Total_Assets'] >= current_target].head(1)
        if not reach_row.empty:
            curr_date = reach_row['Date'].iloc[0]
            days_taken = (curr_date - last_date).days
            if days_taken < 1: days_taken = 1
            m_label = "****" if privacy_mode else f"{int(current_target/10000)}w"
            milestones_res.append({
                "里程碑": m_label, "所用天数": days_taken, "达成日期": curr_date.strftime("%Y-%m-%d")
            })
            last_date = curr_date
            current_target += step
        else:
            break
    return pd.DataFrame(milestones_res)

# =========================================================
#  核心逻辑：如果拿到数据，填充 KPI 占位符 和 其他 Tabs
# =========================================================
if data_source:
    df, monthly_diff, season_pivot = load_and_process_data(data_source, start_dt)
    
    # 1. 填充顶部的 KPI (使用之前定义的占位符)
    with kpi_placeholder:
        title_goal = "****" if privacy_mode else f"¥{target_goal:,.0f}"
        st.subheader(f"📊 财务看板 (目标: {title_goal})")
        
        curr_total = df['Total_Assets'].iloc[-1]
        curr_stage = df['Stage'].iloc[-1]
        last_change = df['Change'].iloc[-1]
        
        # 计算速率
        stage_df = df[df['Stage'] == curr_stage]
        stage_velocity = 0
        if len(stage_df) > 1:
            stage_growth = stage_df['Total_Assets'].iloc[-1] - stage_df['Total_Assets'].iloc[0]
            stage_days = (stage_df['Date'].max() - stage_df['Date'].min()).days
            if stage_days > 0: stage_velocity = stage_growth / stage_days
        
        one_year_ago = df['Date'].iloc[-1] - timedelta(days=365)
        recent_year_df = df[df['Date'] >= one_year_ago]
        display_velocity = 0
        if len(recent_year_df) > 1:
            recent_growth = recent_year_df['Total_Assets'].iloc[-1] - recent_year_df['Total_Assets'].iloc[0]
            recent_days = (recent_year_df['Date'].max() - recent_year_df['Date'].min()).days
            if recent_days > 0: display_velocity = recent_growth / recent_days

        kpi_total = fmt_money(curr_total, True)
        kpi_change = "****" if privacy_mode else f"{last_change:+,.0f}"

        # 移动端优化的 KPI 布局
        row1 = st.columns(2)
        row1[0].metric("当前总资产", kpi_total, f"{kpi_change}")
        row1[1].metric("当前阶段", curr_stage)
        
        row2 = st.columns(2)
        row2[0].metric("近365日均积累", f"¥{display_velocity:,.0f} /天")
        row2[1].metric("现金占比", f"{(df['Bank'].iloc[-1]/curr_total)*100:.1f}%")
        st.divider()

    # 2. 填充各个图表 Tab
    with tab1:
        st.subheader("📈 资产演变趋势")
        fig_trend = px.area(df, x='Date', y=['资产类型:银行', '资产类型:投资'], 
                             color_discrete_map={"资产类型:银行": "#7fb3d5", "资产类型:投资": "#5b5ea6"})
        for m in milestones:
            if m['date'] >= df['Date'].min():
                fig_trend.add_vline(x=m['date'].timestamp() * 1000, line_dash="dash", line_color="orange")
        mask_fig(fig_trend, axis='y')
        st.plotly_chart(fig_trend, use_container_width=True)
        
        st.subheader("🌔 月度净盈亏")
        m_data = monthly_diff.reset_index()
        m_data.columns = ['月份', '金额']
        fig_monthly = px.bar(m_data, x='月份', y='金额', color='金额', color_continuous_scale='RdYlGn')
        mask_fig(fig_monthly, axis='y')
        if privacy_mode: fig_monthly.update_coloraxes(showscale=False)
        st.plotly_chart(fig_monthly, use_container_width=True)

    with tab2:
        st.subheader("⏱️ 财富进阶速率")
        v_df = calculate_milestone_velocity(df, velocity_step)
        if not v_df.empty:
            fig_v = px.bar(v_df, x='里程碑', y='所用天数', text='所用天数', color='所用天数', color_continuous_scale='RdYlBu_r')
            st.plotly_chart(fig_v, use_container_width=True)
        
        st.subheader("🗓️ 年度速率")
        df['Year'] = df['Date'].dt.year
        yearly_summary = []
        for year, group in df.groupby('Year'):
            if len(group) > 1:
                growth = group['Total_Assets'].iloc[-1] - group['Total_Assets'].iloc[0]
                days = (group['Date'].max() - group['Date'].min()).days
                if days > 0:
                    yearly_summary.append({"年份": str(year), "日均增长": growth/days})
        if yearly_summary:
            y_df = pd.DataFrame(yearly_summary)
            fig_year = px.bar(y_df, x='年份', y='日均增长', text='日均增长', color='日均增长', color_continuous_scale='GnBu')
            if privacy_mode: 
                fig_year.update_traces(texttemplate="****")
                fig_year.update_coloraxes(showscale=False)
            st.plotly_chart(fig_year, use_container_width=True)

    with tab3:
        st.subheader("📊 账目分类")
        full_stats = df[df['Change'] != 0].groupby('Tag')['Change'].sum().reset_index()
        top_exp = full_stats.nsmallest(10, 'Change')
        top_inc = full_stats.nlargest(10, 'Change')
        tag_stats = pd.concat([top_exp, top_inc]).drop_duplicates().sort_values('Change')
        fig_tag = px.bar(tag_stats, x='Change', y='Tag', orientation='h', color='Change', color_continuous_scale='RdBu', color_continuous_midpoint=0, height=600)
        mask_fig(fig_tag, axis='x')
        if privacy_mode: fig_tag.update_coloraxes(showscale=False)
        st.plotly_chart(fig_tag, use_container_width=True)

    with tab4:
        st.subheader("🚀 预测")
        if stage_velocity > 0:
            remaining = target_goal - curr_total
            if remaining > 0:
                days_needed = remaining / stage_velocity
                pred_date = (datetime.now() + timedelta(days=days_needed)).date()
                st.info(f"预计达成日期：{pred_date}")
            else:
                st.success("已达成目标！")
        
        st.subheader("🔥 季节性热力图")
        if not season_pivot.empty:
            fig_heat = px.imshow(season_pivot.fillna(0)/1000, aspect="auto", color_continuous_scale='RdYlGn')
            if privacy_mode: 
                fig_heat.update_coloraxes(showscale=False)
                fig_heat.update_traces(texttemplate="")
            st.plotly_chart(fig_heat, use_container_width=True)

else:
    # 如果没有数据，且不在设置页，给个提示
    with kpi_placeholder:
        st.info("👋 欢迎！请点击下方的 **[⚙️ 设置]** 标签页来绑定数据。")
