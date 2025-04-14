FROM python:3.10-bullseye
WORKDIR /app
RUN pip install --upgrade pip && pip install numpy matplotlib seaborn scikit-learn yfinance scipy statsmodels sympy bokeh plotly dash networkx pyvis pandas agixtsdk