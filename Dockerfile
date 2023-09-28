FROM python:3.10
WORKDIR /app
RUN pip install numpy matplotlib seaborn scikit-learn yfinance scipy statsmodels sympy bokeh plotly dash networkx pyvis pandas