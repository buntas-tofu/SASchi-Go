# Rounded scalar source/control witness for principal and maintainer review.
# Independent base-R testbed evidence; no live SAS or physical SAS log claim.
limit <- 2147483647
normal <- .Machine$double.xmin
hex <- function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
number_text <- function(x) if(is.na(x)) '.' else sprintf('%.17g',x)
numeric_operand <- function(x) {
  if(is.nan(x)) stop('NaN is not ordinary missing')
  if(is.na(x)) return(NA_real_)
  if(!is.finite(x) || abs(x)>limit || (x!=0 && abs(x)<normal)) stop('numeric bound')
  if(x==0) 0 else x
}
bound <- function(kind,text) {
  if(kind=='missing') return(NA_real_)
  if(kind!='number') stop('ordinary numeric operand required')
  numeric_operand(suppressWarnings(as.numeric(text)))
}
arithmetic <- function(op,a,b) {
  a <- numeric_operand(a);b <- numeric_operand(b)
  if(op=='**' && !is.na(b) && (b!=trunc(b) || b<0 || b>32 || (!is.na(a) && a==0 && b==0))) stop('power domain')
  if(op=='/' && !is.na(b) && b==0) stop('division domain')
  if(is.na(a) || is.na(b)) return(NA_real_)
  q <- switch(op,'+'=a+b,'-'=a-b,'*'=a*b,'/'=a/b,'**'=a^b,stop('operator'))
  if(q==0 && a!=0 && b!=0 && op %in% c('*','/','**')) stop('underflow')
  numeric_operand(q)
}
call <- function(name,values) {
  if(name=='constant') {
    if(length(values)!=1L || !identical(values[[1]],'pi')) stop('constant domain')
    return(pi)
  }
  if(length(values)!=1L) stop('arity')
  x <- numeric_operand(values[[1]])
  if(is.na(x)) return(NA_real_)
  if(name %in% c('sin','cos') && abs(x)>pi) stop('radian domain')
  if(name=='tan' && abs(x)>pi/4) stop('tangent domain')
  if(name %in% c('arsin','arcos') && abs(x)>1) stop('inverse domain')
  value <- switch(name,sin=sin(x),cos=cos(x),tan=tan(x),arsin=asin(x),
                  arcos=acos(x),atan=atan(x),stop('function'))
  numeric_operand(value)
}
logical_number <- function(x) {
  if(is.na(x)) return('.')
  if(!is.finite(x)) stop('output finite')
  if(x==0) return('0')
  if(x==trunc(x)) {
    if(abs(x)>99999999999) stop('output integer magnitude')
    return(sprintf('%.0f',x))
  }
  if(abs(x)<1e-4 || abs(x)>=1e9) stop('output fraction magnitude')
  width <- nchar(sprintf('%.0f',trunc(abs(x))))
  places <- 12L-as.integer(x<0)-width-1L
  fmt <- paste0('%.',places,'f')
  token <- sprintf(fmt,x)
  if(nchar(token)>12L) stop('output carry width')
  # Different host-language rounding with a conservative17ULP stability witness.
  # The implementation's exact rational guard is16ULP; these cases stay clear.
  exponent <- as.numeric(strsplit(sprintf('%a',abs(x)),'p',fixed=TRUE)[[1]][2])
  step <- 2^(exponent-52)
  if(sprintf(fmt,x-17*step)!=token || sprintf(fmt,x+17*step)!=token) stop('decimal midpoint')
  token <- sub('0+$','',token);token <- sub('\\.$','',token)
  if(token=='-0') '0' else token
}
record <- function(values) {
  text <- paste0(paste(vapply(values,logical_number,''),collapse=' '),' ')
  if(nchar(text)>64L) stop('output row width')
  text
}
capture <- function(pattern,text) {
  match <- regmatches(text,regexec(paste0('(?i)^',pattern,'$'),text,perl=TRUE))[[1]]
  if(length(match)) match[-1] else NULL
}
scan_program <- function(path) {
  text <- paste(readLines(path,warn=FALSE),collapse='\n')
  chars <- strsplit(text,'',fixed=TRUE)[[1]]
  at <- 1L;buffer <- '';statements <- character();comment <- FALSE;quote <- ''
  while(at<=length(chars)) {
    ch <- chars[at];after <- if(at<length(chars)) chars[at+1L] else ''
    if(comment) {
      if(ch=='*' && after=='/') {comment <- FALSE;buffer <- paste0(buffer,' ');at <- at+2L} else at <- at+1L
    } else if(nzchar(quote)) {
      buffer <- paste0(buffer,ch);at <- at+1L
      if(ch==quote) {
        if(after==quote) {buffer <- paste0(buffer,after);at <- at+1L} else quote <- ''
      }
    } else if(ch=='/' && after=='*') {comment <- TRUE;at <- at+2L}
    else if(ch %in% c("'",'"')) {quote <- ch;buffer <- paste0(buffer,ch);at <- at+1L}
    else if(ch==';') {
      statement <- trimws(buffer);if(!nzchar(statement)) stop('null source statement')
      statements <- c(statements,statement);buffer <- '';at <- at+1L
    } else {buffer <- paste0(buffer,ch);at <- at+1L}
  }
  if(comment || nzchar(quote) || nzchar(trimws(buffer))) stop('unconsumed source')
  statements
}
parse_expr <- function(text) {
  pattern <- "'[^']*'|\"[^\"]*\"|[0-9]+(?:\\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\\.[0-9]+(?:[eE][+-]?[0-9]+)?|[a-z_]\\w*|\\*\\*|[.(),+*/-]"
  tokens <- regmatches(tolower(text),gregexpr(pattern,tolower(text),perl=TRUE))[[1]]
  if(!length(tokens) || paste(tokens,collapse='')!=gsub('[[:space:]]','',tolower(text))) stop('expression tokens')
  at <- 1L
  peek <- function() if(at<=length(tokens)) tokens[at] else ''
  take <- function(expected=NULL) {
    if(at>length(tokens)) stop('expression ends early')
    x <- tokens[at];at <<- at+1L
    if(!is.null(expected) && x!=expected) stop('required expression token')
    x
  }
  atom <- function() {
    x <- take()
    if(x=='(') {value <- expression();take(')');return(value)}
    if(x=='.') return(list(kind='number',value=NA_real_))
    if(grepl('^[0-9.]',x)) return(list(kind='number',value=numeric_operand(as.numeric(x))))
    if(substr(x,1,1) %in% c("'",'"')) return(list(kind='string',value=substr(x,2,nchar(x)-1)))
    if(!grepl('^[a-z_]\\w*$',x,perl=TRUE)) stop('primary token')
    if(peek()=='(') {
      take('(');args <- list()
      if(peek()!=')') {
        args[[1]] <- expression()
        while(peek()==',') {take(',');args[[length(args)+1L]] <- expression()}
      }
      take(')');return(list(kind='call',name=x,args=args))
    }
    list(kind='variable',name=x)
  }
  power <- function() {
    if(peek() %in% c('+','-')) {op <- take();return(list(kind='unary',op=op,value=power()))}
    value <- atom()
    if(peek()=='**') {take('**');value <- list(kind='binary',op='**',left=value,right=power())}
    value
  }
  product <- function() {
    value <- power()
    while(peek() %in% c('*','/')) {op <- take();value <- list(kind='binary',op=op,left=value,right=power())}
    value
  }
  expression <- function() {
    value <- product()
    while(peek() %in% c('+','-')) {op <- take();value <- list(kind='binary',op=op,left=value,right=product())}
    value
  }
  value <- expression();if(at<=length(tokens)) stop('unconsumed expression');value
}
program <- function(path) {
  statements <- scan_program(path);at <- 1L
  cat('STATEMENTS:',length(statements),'\n',sep='')
  while(at<=length(statements)) {
    header <- capture('data\\s+([a-z_]\\w*)',statements[at]);at <- at+1L
    if(is.null(header)) stop('DATA header required')
    name <- tolower(header);schema <- character();retained <- character();explicit <- FALSE
    add_name <- function(n) if(!(n %in% schema)) schema <<- c(schema,n)
    discover <- function(expr) {
      if(expr$kind=='variable') add_name(expr$name)
      if(expr$kind=='binary') {discover(expr$left);discover(expr$right)}
      if(expr$kind=='unary') discover(expr$value)
      if(expr$kind=='call') for(x in expr$args) discover(x)
    }
    parse_op <- function(text,nested=FALSE) {
      loop <- capture('do\\s+([a-z_]\\w*)\\s*=\\s*([+-]?[0-9]+)\\s+to\\s+([+-]?[0-9]+)(?:\\s+by\\s+([+-]?[0-9]+))?',text)
      condition <- capture('if\\s+(.+?)\\s*(>=|<=|>|<|=|ne)\\s*(.+?)\\s+then\\s+(.+)',text)
      put <- capture('put\\s+([a-z_]\\w*(?:\\s+[a-z_]\\w*)*)',text)
      assignment <- capture('([a-z_]\\w*)\\s*=\\s*(.+)',text)
      summation <- capture('([a-z_]\\w*)\\s*\\+\\s*(.+)',text)
      if(!is.null(loop)) {
        add_name(loop[1]);increment <- if(nzchar(loop[4])) as.numeric(loop[4]) else 1
        if(increment==0) stop('zero loop increment')
        return(list(kind='loop',name=loop[1],start=as.numeric(loop[2]),stop=as.numeric(loop[3]),increment=increment,body=parse_body(TRUE)))
      }
      if(!is.null(condition)) {
        left <- parse_expr(condition[1]);right <- parse_expr(condition[3]);discover(left);discover(right)
        return(list(kind='if',op=condition[2],left=left,right=right,body=list(parse_op(condition[4],nested))))
      }
      if(!is.null(put)) {
        names <- strsplit(put,'\\s+',perl=TRUE)[[1]];for(n in names) add_name(n)
        return(list(kind='put',names=names))
      }
      if(text=='output') {explicit <<- TRUE;return(list(kind='output'))}
      if(!is.null(assignment) || !is.null(summation)) {
        match <- if(!is.null(assignment)) assignment else summation
        add_name(match[1]);value <- parse_expr(match[2]);discover(value)
        if(is.null(assignment)) retained <<- unique(c(retained,match[1]))
        return(list(kind=if(is.null(assignment)) 'sum' else 'assign',name=match[1],value=value))
      }
      stop(paste('unhandled source statement',text))
    }
    parse_body <- function(nested=FALSE) {
      body <- list()
      repeat {
        if(at>length(statements)) stop('missing step/loop terminator')
        text <- tolower(statements[at]);at <<- at+1L
        if(text=='end') {if(!nested) stop('unexpected END');return(body)}
        if(text=='run') {if(nested) stop('RUN inside loop');return(body)}
        body[[length(body)+1L]] <- parse_op(text,nested)
      }
    }
    body <- parse_body();row <- setNames(as.list(rep(NA_real_,length(schema))),schema)
    for(n in retained) row[[n]] <- 0
    output <- list();logs <- character();trips <- 0L
    evaluate <- function(expr) {
      if(expr$kind %in% c('number','string')) return(expr$value)
      if(expr$kind=='variable') return(row[[expr$name]])
      if(expr$kind=='unary') return(numeric_operand(if(expr$op=='-') -evaluate(expr$value) else evaluate(expr$value)))
      if(expr$kind=='binary') return(arithmetic(expr$op,evaluate(expr$left),evaluate(expr$right)))
      if(expr$kind=='call') return(call(expr$name,lapply(expr$args,evaluate)))
      stop('unhandled expression')
    }
    perform <- function(body) {
      for(op in body) {
        if(op$kind=='assign') row[[op$name]] <<- evaluate(op$value)
        else if(op$kind=='sum') {
          value <- evaluate(op$value);old <- row[[op$name]]
          row[[op$name]] <<- arithmetic('+',if(is.na(old)) 0 else old,if(is.na(value)) 0 else value)
        } else if(op$kind=='output') output[[length(output)+1L]] <<- row[schema]
        else if(op$kind=='put') logs <<- c(logs,record(row[op$names]))
        else if(op$kind=='if') {
          a <- evaluate(op$left);b <- evaluate(op$right)
          truth <- if(is.na(a) || is.na(b)) FALSE else switch(op$op,'>'=a>b,'<'=a<b,'>='=a>=b,'<='=a<=b,'='=a==b,ne=a!=b)
          if(truth) perform(op$body)
        } else if(op$kind=='loop') {
          row[[op$name]] <<- op$start
          test <- function() if(op$increment>0) row[[op$name]]<=op$stop else row[[op$name]]>=op$stop
          while(test()) {
            trips <<- trips+1L;if(trips>10000L) stop('loop budget')
            perform(op$body);row[[op$name]] <<- arithmetic('+',row[[op$name]],op$increment)
          }
        } else stop('unhandled runtime operation')
      }
    }
    perform(body);if(!explicit) output[[1L]] <- row[schema]
    encode <- function(r) paste(vapply(r,number_text,''),collapse=',')
    cat('STEP:',name,'\n','SCHEMA:',paste(schema,collapse=','),'\n','TRIPS:',trips,'\n','FINAL:',encode(row[schema]),'\n',sep='')
    if(name!='_null_') for(snapshot in output) cat('ROW:',encode(snapshot),'\n',sep='')
    for(log in logs) cat('LOG:',hex(log),'\n',sep='')
  }
}
args <- commandArgs(trailingOnly=TRUE)
if(args[1]=='program') {program(args[2])} else if(args[1]=='cases') {
  cases <- read.csv(args[2],colClasses='character',na.strings=NULL)
  for(i in seq_len(nrow(cases))) {
    r <- cases[i,]
    answer <- tryCatch({
      if(r$op=='put') {
        if(r$a_kind=='missing') a <- NA_real_
        else if(r$a_kind=='number') {a <- as.numeric(r$a);if(is.nan(a)) stop('NaN output')}
        else stop('output type')
        b <- 0
      } else {a <- bound(r$a_kind,r$a);b <- bound(r$b_kind,r$b)}
      value <- if(r$op=='put') logical_number(a) else if(r$op %in% c('+','-','*','/','**')) arithmetic(r$op,a,b) else call(r$op,list(a))
      paste0('OK:',if(r$op=='put') hex(value) else number_text(value))
    },error=function(e) 'REFUSE')
    cat(r$id,':',answer,'\n',sep='')
  }
} else stop('unknown witness mode')
